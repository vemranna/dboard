import smtplib
from dataclasses import dataclass
from datetime import datetime
from email import message_from_string
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests
import streamlit as st
import yaml


CONFIG_PATH = Path("config.yml")
DEFAULT_FOLDER = "INBOX"


@dataclass
class AppConfig:
    api_base_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    sender_email: str


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy config.yml.example to config.yml and update values."
        )

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    api = data.get("greenmail_api", {})
    smtp = data.get("smtp", {})

    return AppConfig(
        api_base_url=api.get("base_url", "http://localhost:8080").rstrip("/"),
        smtp_host=smtp.get("host", "localhost"),
        smtp_port=int(smtp.get("port", 3025)),
        smtp_username=smtp.get("username", ""),
        smtp_password=smtp.get("password", ""),
        smtp_use_tls=bool(smtp.get("use_tls", False)),
        sender_email=smtp.get("sender_email", "noreply@example.com"),
    )


def fetch_users(cfg: AppConfig) -> list[dict[str, Any]]:
    response = requests.get(f"{cfg.api_base_url}/api/user", timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_messages(cfg: AppConfig, user_identifier: str, folder: str = DEFAULT_FOLDER) -> list[dict[str, Any]]:
    response = requests.get(
        f"{cfg.api_base_url}/api/user/{user_identifier}/messages/{folder}", timeout=10
    )
    response.raise_for_status()
    return response.json()


def parse_mime(mime_message: str) -> dict[str, Any]:
    parsed = message_from_string(mime_message)
    from_addr = parsed.get("From", "")
    subject = parsed.get("Subject", "")
    date_raw = parsed.get("Date", "")

    date_value = ""
    if date_raw:
        try:
            dt = parsedate_to_datetime(date_raw)
            if isinstance(dt, datetime):
                date_value = dt.strftime("%Y-%m-%d %H:%M:%S %z")
        except Exception:
            date_value = date_raw

    has_attachment = any(part.get_filename() for part in parsed.walk())

    return {
        "from": from_addr,
        "subject": subject,
        "date": date_value,
        "has_attachment": has_attachment,
    }


def top_recent_messages(messages: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    processed = []
    for msg in messages:
        parsed = parse_mime(msg.get("mimeMessage", ""))
        parsed["uid"] = msg.get("uid")
        processed.append(parsed)

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        return (0 if item["date"] else 1, item["date"])

    processed.sort(key=sort_key, reverse=True)
    return processed[:limit]


def send_reply(
    cfg: AppConfig,
    to_email: str,
    subject: str,
    body: str,
    attachment_name: str | None = None,
    attachment_bytes: bytes | None = None,
) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment_name and attachment_bytes is not None:
        msg.add_attachment(
            attachment_bytes,
            maintype="application",
            subtype="octet-stream",
            filename=attachment_name,
        )

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
        if cfg.smtp_use_tls:
            server.starttls()
        if cfg.smtp_username:
            server.login(cfg.smtp_username, cfg.smtp_password)
        server.send_message(msg)


def app() -> None:
    st.set_page_config(page_title="GreenMail Dashboard", layout="wide")
    st.title("GreenMail Dashboard")
    st.caption("Mailbox monitoring and quick reply")

    try:
        cfg = load_config(CONFIG_PATH)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    try:
        users = fetch_users(cfg)
    except Exception as exc:
        st.error(f"Unable to load users from GreenMail API: {exc}")
        return

    if not users:
        st.info("No mailboxes found.")
        return

    user_options = {f"{u.get('email')} ({u.get('login')})": u for u in users}
    selected_label = st.selectbox("Select mailbox", list(user_options.keys()))
    selected_user = user_options[selected_label]
    email = selected_user.get("email") or selected_user.get("login")

    st.subheader("Top 5 recent messages")

    messages: list[dict[str, Any]] = []
    try:
        raw_messages = fetch_messages(cfg, email, DEFAULT_FOLDER)
        messages = top_recent_messages(raw_messages)
    except Exception as exc:
        st.error(f"Unable to fetch messages: {exc}")

    if messages:
        st.dataframe(
            [
                {
                    "uid": m["uid"],
                    "sender": m["from"],
                    "subject": m["subject"],
                    "date": m["date"],
                    "attachment_status": "Yes" if m["has_attachment"] else "No",
                }
                for m in messages
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No messages in mailbox.")

    st.subheader("Reply to a message")
    if not messages:
        st.write("Select a mailbox with messages to enable reply.")
        return

    selected_uid = st.selectbox("Message UID", [m["uid"] for m in messages])
    selected_message = next(m for m in messages if m["uid"] == selected_uid)

    with st.form("reply_form"):
        to_email = st.text_input("To", value=selected_message["from"])
        subject = st.text_input("Subject", value=f"Re: {selected_message['subject']}")
        body = st.text_area("Body", value="", height=180)
        attachment = st.file_uploader("Attachment", accept_multiple_files=False)
        submitted = st.form_submit_button("Send reply")

    if submitted:
        attachment_bytes = attachment.getvalue() if attachment else None
        attachment_name = attachment.name if attachment else None
        try:
            send_reply(
                cfg,
                to_email=to_email,
                subject=subject,
                body=body,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
            st.success("Reply sent successfully.")
        except Exception as exc:
            st.error(f"Failed to send reply: {exc}")


if __name__ == "__main__":
    app()
