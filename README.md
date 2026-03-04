# GreenMail Dashboard

Simple Streamlit dashboard for GreenMail monitoring and quick replies.

## Features
- Shows all GreenMail mailboxes from `/api/user`
- For the selected mailbox, shows top 5 recent messages with:
  - sender
  - subject
  - date
  - attachment status
- Allows replying to selected message with editable:
  - subject
  - body
  - optional file attachment

## Configuration
Copy the example file and update values:

```bash
cp config.yml.example config.yml
```

`config.yml` keys:
- `greenmail_api.base_url`: GreenMail API base URL
- `smtp.host`, `smtp.port`, `smtp.username`, `smtp.password`, `smtp.use_tls`, `smtp.sender_email`

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
