"""HTML page templates for OAuth flow."""

import html as html_lib
import json as json_lib


def page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html_lib.escape(title)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #f5f7fb; color: #1a1a2e; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }}
        .card {{ background: white; border-radius: 12px; padding: 40px; max-width: 480px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
        h1 {{ font-size: 24px; margin-bottom: 16px; }}
        p {{ color: #555; line-height: 1.6; margin-bottom: 12px; }}
        .btn {{ display: inline-block; padding: 10px 24px; border-radius: 8px; font-size: 14px; font-weight: 500; text-decoration: none; cursor: pointer; border: none; }}
        .btn-primary {{ background: #5563ff; color: white; }}
        .btn-primary:hover {{ background: #4452ee; }}
        .btn-secondary {{ background: #e8ebf0; color: #333; }}
        .success {{ color: #16a34a; }}
        .error {{ color: #dc2626; }}
        .select-item {{ border: 2px solid #e8ebf0; border-radius: 8px; padding: 16px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s; }}
        .select-item:hover {{ border-color: #c0c8d8; }}
        .select-item.selected {{ border-color: #5563ff; background: rgba(85,99,255,0.04); }}
        .section-label {{ font-size: 13px; font-weight: 600; color: #888; text-transform: uppercase; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="card">{body}</div>
</body>
</html>"""


def error_page(title: str, message: str, retry_url: str = None) -> str:
    retry = ""
    if retry_url:
        safe_url = html_lib.escape(retry_url)
        retry = f'<a href="{safe_url}" class="btn btn-secondary">Try again</a>'
    body = f"""
        <h1 class="error">{html_lib.escape(title)}</h1>
        <p>{html_lib.escape(message)}</p>
        {retry}
    """
    return page_shell(title, body)


def success_page(workspace_name: str, redirect_url: str = None) -> str:
    safe_name = html_lib.escape(workspace_name)
    redirect_script = ""
    cta = ""
    if redirect_url:
        safe_url = html_lib.escape(redirect_url)
        redirect_script = f'<script>setTimeout(function(){{ window.location.href = "{safe_url}"; }}, 3000);</script>'
        cta = f'<a href="{safe_url}" class="btn btn-primary">Continue</a>'
    body = f"""
        <div style="text-align:center;">
            <h1 class="success">You're All Set!</h1>
            <p>Your Sokosumi account is connected using <strong>{safe_name}</strong>.</p>
            <p>You can now close this tab and continue chatting.</p>
            {cta}
            {redirect_script}
        </div>
    """
    return page_shell("Connected", body)


def select_account_page(state: str, personal_credits: float, organizations: list) -> str:
    org_items = ""
    for org in organizations:
        org_name = html_lib.escape(org["name"])
        org_credits = org.get("credits", 0)
        js_id = html_lib.escape(json_lib.dumps(str(org["id"])))
        js_name = html_lib.escape(json_lib.dumps(org["name"]))
        org_items += f"""
        <div class="select-item" onclick="selectAccount('organization', {js_id}, {js_name}, this)">
            <div><strong>{org_name}</strong></div>
            <div style="color:#16a34a;font-size:14px;">{org_credits:.2f} credits</div>
        </div>"""

    js_state = json_lib.dumps(state)
    body = f"""
        <h1>Select Workspace</h1>
        <p>Choose where tasks should be billed:</p>
        <div style="margin: 20px 0;">
            <div class="section-label">Personal</div>
            <div class="select-item" onclick="selectAccount('personal', null, 'Personal Workspace', this)">
                <div><strong>Personal Workspace</strong></div>
                <div style="color:#16a34a;font-size:14px;">{personal_credits:.2f} credits</div>
            </div>
        </div>
        {"<div style='margin:20px 0;'><div class='section-label'>Organizations</div>" + org_items + "</div>" if org_items else ""}
        <button class="btn btn-primary" id="confirmBtn" disabled onclick="confirmSelection()"
                style="width:100%;margin-top:16px;">
            Select a workspace above
        </button>
        <script>
        let selectedType = null, selectedId = null, selectedName = null;
        function selectAccount(type, id, name, el) {{
            selectedType = type; selectedId = id; selectedName = name;
            document.querySelectorAll('.select-item').forEach(e => e.classList.remove('selected'));
            el.classList.add('selected');
            const btn = document.getElementById('confirmBtn');
            btn.disabled = false;
            btn.textContent = 'Use ' + name;
        }}
        function confirmSelection() {{
            if (!selectedType) return;
            let url = '/oauth/confirm?state=' + encodeURIComponent({js_state}) + '&account_type=' + encodeURIComponent(selectedType);
            if (selectedId) url += '&org_id=' + encodeURIComponent(selectedId);
            window.location.href = url;
        }}
        </script>
    """
    return page_shell("Select Workspace", body)
