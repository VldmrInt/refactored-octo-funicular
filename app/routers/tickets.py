from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Message, Ticket, TicketFile, User
from app.bot import notify_new_ticket, notify_status_changed, notify_assigned, notify_urgent

router = APIRouter(prefix="/tickets", tags=["tickets"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class FileOut(BaseModel):
    id: int
    filename: str
    stored_path: str
    filesize: int

    model_config = {"from_attributes": True}


class UserShort(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class TicketOut(BaseModel):
    id: int
    number: str
    status: str
    is_urgent: bool
    title: str
    description: str
    steps: str | None
    url: str | None
    author: UserShort
    assignee: UserShort | None
    files: list[FileOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketCreate(BaseModel):
    title: str
    description: str
    steps: str | None = None
    url: str | None = None
    is_urgent: bool = False


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    steps: str | None = None
    url: str | None = None
    is_urgent: bool | None = None


class StatusUpdate(BaseModel):
    status: str


class UrgentUpdate(BaseModel):
    is_urgent: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, list[str]] = {
    "new": ["in_progress"],
    "in_progress": ["on_pause", "biz_review", "closed"],
    "on_pause": ["in_progress"],
    "biz_review": ["in_progress", "closed"],
    "closed": ["reopened"],
    "reopened": ["in_progress"],
}

AUTHOR_ALLOWED_TARGETS = {"closed", "reopened"}  # author can only go to these
SUPPORT_ALLOWED_TARGETS = {"in_progress", "on_pause", "biz_review", "closed"}


def _generate_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = (
        db.query(func.count(Ticket.id))
        .filter(extract("year", Ticket.created_at) == year)
        .scalar()
        or 0
    )
    return f"#{year}-{count + 1:03d}"


def _add_system_message(db: Session, ticket_id: int, text: str) -> None:
    msg = Message(ticket_id=ticket_id, sender_id=None, sender_role="system", text=text)
    db.add(msg)


def _touch_ticket(ticket: Ticket) -> None:
    ticket.updated_at = datetime.now(timezone.utc)


STATUS_LABELS = {
    "new": "Новое",
    "in_progress": "В работе",
    "on_pause": "На паузе",
    "biz_review": "Проверка бизнесом",
    "closed": "Закрытое",
    "reopened": "Переоткрытое",
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TicketOut])
def list_tickets(
    filter: str = Query("mine", pattern="^(all|mine|closed)$"),
    urgent: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Ticket)

    if filter == "all":
        if current_user.role not in ("support", "admin"):
            raise HTTPException(status_code=403, detail="Access denied")
    elif filter == "mine":
        q = q.filter(Ticket.author_id == current_user.id)
    elif filter == "closed":
        q = q.filter(Ticket.status == "closed")
        if current_user.role == "author":
            q = q.filter(Ticket.author_id == current_user.id)

    if urgent is not None:
        q = q.filter(Ticket.is_urgent == urgent)

    tickets = q.order_by(Ticket.updated_at.desc()).all()
    return tickets


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = _generate_number(db)
    ticket = Ticket(
        number=number,
        author_id=current_user.id,
        status="new",
        is_urgent=payload.is_urgent,
        title=payload.title,
        description=payload.description,
        steps=payload.steps,
        url=payload.url,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Notify support/admins asynchronously (fire-and-forget)
    background_tasks.add_task(notify_new_ticket, ticket, current_user)

    return ticket


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _check_read_access(ticket, current_user)
    return ticket


@router.put("/{ticket_id}", response_model=TicketOut)
def edit_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can edit")
    if ticket.status != "new":
        raise HTTPException(status_code=403, detail="Editing only allowed in 'new' status")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(ticket, field, value)
    _touch_ticket(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.put("/{ticket_id}/status", response_model=TicketOut)
def change_status(
    ticket_id: int,
    payload: StatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    new_status = payload.status
    allowed_from_current = VALID_TRANSITIONS.get(ticket.status, [])

    if new_status not in allowed_from_current:
        raise HTTPException(
            status_code=400,
            detail=f"Transition {ticket.status} → {new_status} is not allowed",
        )

    role = current_user.role
    if role == "author":
        # Author can only close from biz_review or reopen from closed
        if new_status not in ("closed", "reopened"):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        if new_status == "closed" and ticket.status != "biz_review":
            raise HTTPException(status_code=403, detail="Author can close only from biz_review")
        if new_status == "reopened" and ticket.status != "closed":
            raise HTTPException(status_code=403, detail="Author can reopen only closed tickets")
        if ticket.author_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your ticket")
    elif role not in ("support", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    old_status = ticket.status
    ticket.status = new_status
    _touch_ticket(ticket)

    label_old = STATUS_LABELS.get(old_status, old_status)
    label_new = STATUS_LABELS.get(new_status, new_status)

    if new_status == "closed":
        sys_text = "── Обращение закрыто"
    elif new_status == "reopened":
        sys_text = "── Обращение переоткрыто"
    else:
        sys_text = f"── Статус изменён: {label_old} → {label_new}"

    _add_system_message(db, ticket.id, sys_text)
    db.commit()
    db.refresh(ticket)

    _ = ticket.author  # pre-load relationship while session is open
    background_tasks.add_task(notify_status_changed, ticket, old_status, current_user)

    return ticket


@router.put("/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("support", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.assigned_to is not None:
        raise HTTPException(status_code=400, detail="Ticket already assigned")

    ticket.assigned_to = current_user.id
    if ticket.status == "new":
        old_status = ticket.status
        ticket.status = "in_progress"
        _add_system_message(db, ticket.id, "── Статус изменён: Новое → В работе")
    _touch_ticket(ticket)
    db.commit()
    db.refresh(ticket)

    _ = ticket.author  # pre-load relationship while session is open
    background_tasks.add_task(notify_assigned, ticket, current_user)

    return ticket


@router.put("/{ticket_id}/urgent", response_model=TicketOut)
def toggle_urgent(
    ticket_id: int,
    payload: UrgentUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    role = current_user.role
    if role == "author" and ticket.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")

    ticket.is_urgent = payload.is_urgent
    _touch_ticket(ticket)

    if payload.is_urgent:
        _add_system_message(db, ticket.id, "── Тег «Срочно» установлен")
    else:
        _add_system_message(db, ticket.id, "── Тег «Срочно» снят")

    db.commit()
    db.refresh(ticket)

    if payload.is_urgent:
        background_tasks.add_task(notify_urgent, ticket, current_user)

    return ticket


# ── Access helpers ────────────────────────────────────────────────────────────

def _check_read_access(ticket: Ticket, user: User) -> None:
    if user.role in ("support", "admin"):
        return
    # author sees own tickets or closed ones they authored
    if ticket.author_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Access denied")
