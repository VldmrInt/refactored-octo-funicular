import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import FORBIDDEN_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_DIR
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Message, MessageFile, Ticket, User
from app.routers.tickets import _check_read_access, _touch_ticket
from app.bot import notify_new_message

router = APIRouter(tags=["messages"])


class MessageFileOut(BaseModel):
    id: int
    filename: str
    stored_path: str
    filesize: int

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    ticket_id: int
    sender_id: int | None
    sender_role: str
    text: str
    created_at: datetime
    files: list[MessageFileOut]

    model_config = {"from_attributes": True}


@router.get("/tickets/{ticket_id}/messages", response_model=list[MessageOut])
def get_messages(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _check_read_access(ticket, current_user)

    messages = (
        db.query(Message)
        .filter(Message.ticket_id == ticket_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return messages


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _check_read_access(ticket, current_user)

    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Cannot send messages to a closed ticket")

    msg = Message(
        ticket_id=ticket_id,
        sender_id=current_user.id,
        sender_role=current_user.role,
        text=text,
    )
    db.add(msg)
    db.flush()  # get msg.id

    if file is not None:
        await _attach_file_to_message(db, msg, ticket_id, file)

    _touch_ticket(ticket)
    db.commit()
    db.refresh(msg)

    _ = ticket.author  # pre-load relationship while session is open
    background_tasks.add_task(notify_new_message, ticket, msg, current_user)

    return msg


async def _attach_file_to_message(
    db: Session, msg: Message, ticket_id: int, upload: UploadFile
) -> None:
    suffix = Path(upload.filename or "file").suffix.lower()
    if suffix in FORBIDDEN_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {suffix} is not allowed")

    content = await upload.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    dest_dir = UPLOAD_DIR / str(ticket_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(upload.filename or 'file').name}"
    stored_path = str(Path(str(ticket_id)) / safe_name)

    (UPLOAD_DIR / stored_path).write_bytes(content)

    mf = MessageFile(
        message_id=msg.id,
        filename=upload.filename or "file",
        stored_path=stored_path,
        filesize=len(content),
    )
    db.add(mf)
