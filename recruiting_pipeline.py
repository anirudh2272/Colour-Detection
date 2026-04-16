#!/usr/bin/env python3
"""Starter recruitment intelligence and outreach pipeline (stdlib version)."""

from __future__ import annotations

import argparse
import json
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import unescape
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class JobInput:
    title: str
    company: str
    url: str
    description: str


@dataclass
class CandidateProfile:
    name: str
    target_role: str
    skills: List[str]
    years_experience: str = ""
    summary: str = ""


@dataclass
class Contact:
    full_name: str
    role: str
    relevance: str
    profile_url: str
    email_patterns: List[str]
    confidence: str


@dataclass
class PipelineOutput:
    job: JobInput
    score: float
    matched_keywords: List[str]
    contacts: List[Contact]
    outreach_message: str
    linkedin_message: str
    follow_up_message: str
    strategy_notes: List[str]


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_text(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_page(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def extract_job_description(url: str) -> str:
    html = fetch_page(url)
    text = clean_text(html)
    return text[:12000]


def build_job(item: Dict) -> JobInput:
    description = item.get("description", "").strip()
    if not description and item.get("url"):
        try:
            description = extract_job_description(item["url"])
        except Exception:
            description = ""
    return JobInput(
        title=item["title"],
        company=item["company"],
        url=item.get("url", ""),
        description=description,
    )


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{1,}", text.lower())


def score_job_fit(job: JobInput, profile: CandidateProfile) -> Tuple[float, List[str]]:
    profile_blob = " ".join([profile.target_role, " ".join(profile.skills), profile.summary]).lower()
    job_blob = f"{job.title} {job.description}".lower()

    a = set(tokenize(profile_blob))
    b = set(tokenize(job_blob))
    score = (len(a & b) / len(a | b)) if (a | b) else 0.0

    matched_keywords = sorted([skill for skill in profile.skills if skill.lower() in job_blob], key=str.lower)
    return score, matched_keywords


def duckduckgo_search(query: str, max_results: int = 8) -> List[Tuple[str, str, str]]:
    params = urlencode({"q": query})
    url = f"https://duckduckgo.com/html/?{params}"
    html = fetch_page(url)

    blocks = re.findall(r'<div class="result__body".*?</div>\s*</div>', html, flags=re.S)
    rows = []
    for block in blocks[:max_results]:
        link_match = re.search(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>|<div class="result__snippet"[^>]*>(.*?)</div>', block, flags=re.S)
        if not link_match:
            continue
        link = unescape(link_match.group(1))
        title = clean_text(link_match.group(2))
        snippet = ""
        if snippet_match:
            snippet = clean_text(snippet_match.group(1) or snippet_match.group(2) or "")
        rows.append((title, link, snippet))
    return rows


def _extract_name_and_role(text: str) -> Tuple[Optional[str], Optional[str]]:
    parts = [p.strip() for p in re.split(r"\-|\|", text) if p.strip()]
    if not parts:
        return None, None
    name = None
    role = None
    m = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", parts[0])
    if m:
        name = m.group(1)
    if len(parts) > 1:
        role = parts[1]
    return name, role


def infer_domain(company: str, fallback: str = "company.com") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "", company.lower())
    return f"{cleaned}.com" if cleaned else fallback


def estimate_email_patterns(full_name: str, company_domain: str) -> List[str]:
    tokens = [t for t in re.split(r"\s+", full_name.lower()) if t]
    if len(tokens) < 2:
        return []
    first, last = tokens[0], tokens[-1]
    return [
        f"{first}.{last}@{company_domain}",
        f"{first[0]}{last}@{company_domain}",
        f"{first}@{company_domain}",
    ]


def discover_contacts(job: JobInput, company_domain: str, max_contacts: int = 6) -> List[Contact]:
    queries = [
        f'site:linkedin.com/in "{job.company}" hiring manager {job.title}',
        f'site:linkedin.com/in "{job.company}" recruiter talent acquisition',
        f'site:linkedin.com/in "{job.company}" {job.title} manager',
    ]
    contacts: List[Contact] = []

    for query in queries:
        try:
            results = duckduckgo_search(query, max_results=8)
        except Exception:
            continue
        for title, link, snippet in results:
            if "linkedin.com/in" not in link:
                continue
            full_name, role = _extract_name_and_role(f"{title} - {snippet}")
            if not full_name:
                continue
            role_lc = (role or "").lower()
            if any(k in role_lc for k in ["recruit", "talent acquisition"]):
                relevance = "Likely recruiter supporting this hiring funnel."
                confidence = "Medium"
            elif any(k in role_lc for k in ["manager", "director", "head", "lead"]):
                relevance = "Likely hiring manager or technical decision-maker."
                confidence = "Medium"
            else:
                relevance = "Backup contact in a nearby team function."
                confidence = "Low"

            contacts.append(
                Contact(
                    full_name=full_name,
                    role=role or "Unknown",
                    relevance=relevance,
                    profile_url=link,
                    email_patterns=estimate_email_patterns(full_name, company_domain),
                    confidence=confidence,
                )
            )

    dedup = {}
    for c in contacts:
        dedup[(c.full_name.lower(), c.profile_url)] = c
    ranked = sorted(dedup.values(), key=lambda c: ("recruit" not in c.role.lower(), "manager" not in c.role.lower()))
    return ranked[:max_contacts]


def build_outreach_message(job: JobInput, profile: CandidateProfile, keywords: Sequence[str]) -> str:
    kw = ", ".join(keywords[:4]) if keywords else "the role requirements"
    return (
        f"Hi {{first_name}}, I applied for the {job.title} role at {job.company} and wanted to reach out directly.\n"
        f"My background aligns well with {kw}, including production ownership and fast execution.\n"
        f"I’m targeting {profile.target_role} roles where I can contribute immediate impact.\n"
        "If useful, I can send a concise 5-point fit summary mapped to the JD.\n"
        "Would you be open to a brief 10-minute conversation this week?"
    )


def build_linkedin_message(job: JobInput, keywords: Sequence[str]) -> str:
    kw = ", ".join(keywords[:3]) if keywords else "your core requirements"
    msg = (
        f"Hi {{first_name}} — I applied for {job.title} at {job.company}. "
        f"My experience aligns with {kw}. "
        "Open to connect? I can share a concise fit summary."
    )
    return msg[:300]


def build_follow_up(job: JobInput) -> str:
    return (
        f"Hi {{first_name}}, following up on my note about the {job.title} role at {job.company}. "
        "If this is the wrong inbox, could you point me to the best contact on hiring?"
    )


def send_email(smtp_host: str, smtp_port: int, username: str, password: str, sender: str, recipient: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(msg)


def run_pipeline(payload: Dict, send: bool = False) -> PipelineOutput:
    profile_raw = payload["profile"]
    profile = CandidateProfile(
        name=profile_raw["name"],
        target_role=profile_raw["target_role"],
        skills=profile_raw.get("skills", []),
        years_experience=profile_raw.get("years_experience", ""),
        summary=profile_raw.get("summary", ""),
    )
    job = build_job(payload["job"])
    score, keywords = score_job_fit(job, profile)
    domain = payload.get("company_domain") or infer_domain(job.company)
    contacts = discover_contacts(job, domain)

    if send and contacts:
        email_cfg = payload.get("email", {})
        required = ["smtp_host", "smtp_port", "username", "password", "sender"]
        missing = [k for k in required if k not in email_cfg]
        if missing:
            raise ValueError(f"Missing email config keys: {missing}")
        subject = f"Application: {job.title}"
        body_template = build_outreach_message(job, profile, keywords)
        for c in contacts[:2]:
            if c.email_patterns:
                send_email(
                    email_cfg["smtp_host"],
                    int(email_cfg["smtp_port"]),
                    email_cfg["username"],
                    email_cfg["password"],
                    email_cfg["sender"],
                    c.email_patterns[0],
                    subject,
                    body_template.replace("{first_name}", c.full_name.split()[0]),
                )

    return PipelineOutput(
        job=job,
        score=score,
        matched_keywords=keywords,
        contacts=contacts,
        outreach_message=build_outreach_message(job, profile, keywords),
        linkedin_message=build_linkedin_message(job, keywords),
        follow_up_message=build_follow_up(job),
        strategy_notes=[
            "Contact recruiter first for routing and process visibility.",
            "Contact hiring manager second with technical impact bullets.",
            "Send one clear follow-up after 3 days, then stop.",
        ],
    )


def format_markdown(output: PipelineOutput, domain: str) -> str:
    lines: List[str] = []
    lines.append("## Section 1: Contacts Table")
    if not output.contacts:
        lines.append("No reliable contacts found automatically. Use LinkedIn filters: company + recruiter/hiring manager + role function.")
    else:
        lines.append("| Full Name | Current Role/Title | Likely relevance | LinkedIn profile | Work email format | Confidence |")
        lines.append("|---|---|---|---|---|---|")
        for c in output.contacts:
            lines.append(
                f"| {c.full_name} | {c.role} | {c.relevance} | {c.profile_url} | {', '.join(c.email_patterns)} | {c.confidence} |"
            )

    lines.append("\n## Section 2: Email Guesses")
    lines.append(f"- Likely domain: `{domain}`")
    lines.append("- Pattern confidence: Medium (heuristic, verify with company signals).")
    lines.append("- 2–3 likely variations:")
    lines.append("  - `firstname.lastname@domain`")
    lines.append("  - `flastname@domain`")
    lines.append("  - `firstname@domain`")

    lines.append("\n## Section 3: Outreach Message")
    lines.append(output.outreach_message)

    lines.append("\n## Section 4: Strategy Notes")
    for note in output.strategy_notes:
        lines.append(f"- {note}")

    lines.append("\n### LinkedIn connection message (300 chars max)")
    lines.append(output.linkedin_message)

    lines.append("\n### Follow-up message (after 3 days)")
    lines.append(output.follow_up_message)

    lines.append("\n### Keywords from the job description to mention")
    if output.matched_keywords:
        lines.append("- " + ", ".join(output.matched_keywords))
    else:
        lines.append("- No direct overlap detected. Mention top 5 technical and business terms from the JD manually.")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recruiting intelligence pipeline starter")
    parser.add_argument("--input", required=True, help="Path to JSON input payload")
    parser.add_argument("--output", default="pipeline_output.md", help="Output markdown path")
    parser.add_argument("--send", action="store_true", help="Send emails via SMTP settings in input JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_json(args.input)
    result = run_pipeline(payload, send=args.send)
    domain = payload.get("company_domain") or infer_domain(result.job.company)
    report = format_markdown(result, domain)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
