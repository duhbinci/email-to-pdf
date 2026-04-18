from __future__ import annotations

import html
from datetime import datetime

from email_to_pdf.domain.models import Address, ParsedEmail


class HeaderRenderer:
    def render(self, email: ParsedEmail) -> str:
        rows: list[str] = [self._row("From", self._fmt_address(email.from_))]

        if email.to:
            rows.append(self._row("To", self._fmt_addresses(email.to)))
        if email.cc:
            rows.append(self._row("CC", self._fmt_addresses(email.cc)))
        if email.bcc:
            rows.append(self._row("BCC", self._fmt_addresses(email.bcc)))
        if email.date:
            rows.append(self._row("Date", self._fmt_date(email.date)))
        rows.append(self._row("Subject", html.escape(email.subject or "(no subject)")))

        inner = "\n".join(rows)
        return (
            '<div class="email-header" style="'
            "border-bottom:2px solid #444;padding-bottom:8px;margin-bottom:16px;"
            'font-size:0.9em;line-height:1.6;">\n'
            f"{inner}\n</div>"
        )

    def _row(self, label: str, value: str) -> str:
        return (
            f'<div class="header-row">'
            f'<span class="header-label" style="font-weight:bold;color:#444;min-width:60px;display:inline-block;">'
            f"{html.escape(label)}:</span> "
            f'<span class="header-value">{value}</span>'
            f"</div>"
        )

    def _fmt_address(self, addr: Address) -> str:
        if addr.display_name:
            return f"{html.escape(addr.display_name)} &lt;{html.escape(addr.addr_spec)}&gt;"
        return html.escape(addr.addr_spec)

    def _fmt_addresses(self, addrs: list[Address]) -> str:
        return ", ".join(self._fmt_address(a) for a in addrs)

    def _fmt_date(self, dt: datetime) -> str:
        return html.escape(dt.strftime("%a, %d %b %Y %H:%M:%S %z"))
