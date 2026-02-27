import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import FORBIDDEN_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_DIR
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Ticket, TicketFile, User
from app.routers.tickets import _check_read_access, _touch_ticket

router = APIRouter(tags=["files"])


class TicketFileOut(BaseModel):
    id: int
    filename: str
    stored_path: str
    filesize: int

    model_config = {"from_attributes": True}


@router.post(
    "/tickets/{ticket_id}/files",
    response_model=TicketFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    ticket_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _check_read_access(ticket, current_user)

    suffix = Path(file.filename or "file").suffix.lower()
    if suffix in FORBIDDEN_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {suffix} is not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    dest_dir = UPLOAD_DIR / str(ticket_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename or 'file').name}"
    stored_path = str(Path(str(ticket_id)) / safe_name)

    (UPLOAD_DIR / stored_path).write_bytes(content)

    tf = TicketFile(
        ticket_id=ticket_id,
        filename=file.filename or "file",
        stored_path=stored_path,
        filesize=len(content),
        uploaded_by=current_user.id,
    )
    db.add(tf)
    _touch_ticket(ticket)
    db.commit()
    db.refresh(tf)
    return tf


@router.get("/files/{file_path:path}")
def download_file(
    file_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a file. Access is checked via ticket ownership."""
    # Validate path doesn't escape uploads dir
    full_path = (UPLOAD_DIR / file_path).resolve()
    if not str(full_path).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Check access: find ticket_file or message_file with this stored_path
    tf = db.query(TicketFile).filter(TicketFile.stored_path == file_path).first()
    if tf:
        ticket = db.get(Ticket, tf.ticket_id)
        if ticket:
            _check_read_access(ticket, current_user)
    else:
        # Try message file — resolve ticket via message
        from app.models import Message, MessageFile
        mf = db.query(MessageFile).filter(MessageFile.stored_path == file_path).first()
        if mf:
            msg = db.get(Message, mf.message_id)
            if msg:
                ticket = db.get(Ticket, msg.ticket_id)
                if ticket:
                    _check_read_access(ticket, current_user)
        else:
            raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(full_path), filename=full_path.name)
