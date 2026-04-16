# Recruitment Intelligence + Outreach Starter (1-click friendly)

This repository now includes a **working starter pipeline** to:
- ingest a job post + your profile,
- score fit,
- find likely recruiter/hiring-manager contacts,
- guess email patterns,
- generate outreach + follow-up copy,
- optionally send emails (SMTP).

> Important: Contact discovery is heuristic and should be verified before outreach.

## Files
- `recruiting_pipeline.py` — main pipeline CLI (Python stdlib-only).
- `examples/sample_input.json` — starter payload.
- `colab_starter.ipynb` — 1-click Colab notebook.
- `requirements.txt` — optional/dependency note.

## Quick start (local)

```bash
python recruiting_pipeline.py --input examples/sample_input.json --output report.md
cat report.md
```

## 1-click Colab flow
1. Open `colab_starter.ipynb` in Google Colab.
2. Upload `recruiting_pipeline.py`.
3. Edit `input.json` cell with your job + profile.
4. Run all cells.

## Input JSON schema

```json
{
  "job": {
    "title": "Senior Machine Learning Engineer",
    "company": "ExampleAI",
    "url": "https://company.com/jobs/123",
    "description": "Optional; if missing, pipeline attempts URL extraction"
  },
  "profile": {
    "name": "Your Name",
    "target_role": "Machine Learning Engineer",
    "skills": ["Python", "NLP", "LLM", "AWS"],
    "years_experience": "6+ years",
    "summary": "Short value proposition"
  },
  "company_domain": "exampleai.com",
  "email": {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "you@gmail.com",
    "password": "app-password",
    "sender": "you@gmail.com"
  }
}
```

## Email send mode (optional)

By default, the pipeline only generates output.
To send emails to top contacts:

```bash
python recruiting_pipeline.py --input examples/sample_input.json --output report.md --send
```

## Output format
The report is generated with sections:
1. Contacts Table
2. Email Guesses
3. Outreach Message
4. Strategy Notes

Plus:
- LinkedIn connection message (<=300 chars)
- 3-day follow-up message
- Keywords from job/profile overlap

## Notes
- If no reliable contacts are found, the output tells you how to find them manually.
- Keep outreach compliant with platform terms and privacy laws.
