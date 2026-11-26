"""Editable, plain-text provider correspondence with a fixed placeholder vocabulary."""
from string import Formatter

SUBJECT = "Slow broadband service — {provider} — account {account_reference}"
BODY = """Dear {provider} support team,

I am writing to report consistently slow download speeds on my broadband service.

Account reference: {account_reference}
Advertised download speed: {plan_mbps} Mbps
Measured average: {average_mbps} Mbps
Monitoring period: {window_hours} hours
Successful tests: {sample_count}
Tests below {threshold_mbps} Mbps: {below_count}

The measurements were taken automatically on my Mac using Apple's networkQuality tool. Connection conditions: {connection_notes}

Please investigate the reduced speeds, confirm the minimum guaranteed download speed for my service, and provide a fault reference and an expected resolution date. Please also advise whether any service credit is available under my agreement.

I can provide the timestamped measurement report and raw results to support this request.

Kind regards,
{customer_name}
{user_email}"""


def values(c, rows):
    good = [r for r in rows if r['status'] == 'ok']
    avg = sum(r['download_mbps'] for r in good) / len(good) if good else None
    profile = c.get('profile', {})
    return {
        'provider': profile.get('provider') or 'your broadband provider',
        'account_reference': profile.get('account_reference') or '[account reference]',
        'customer_name': profile.get('customer_name') or '[your name]',
        'user_email': profile.get('user_email') or '[your email]',
        'plan_mbps': f"{c['plan_mbps']:g}",
        'threshold_mbps': f"{c['threshold_mbps']:g}",
        'average_mbps': f'{avg:.1f}' if avg is not None else 'No data yet',
        'window_hours': f"{c['average_hours']:g}",
        'sample_count': str(len(good)),
        'below_count': str(sum(r['download_mbps'] < c['threshold_mbps'] for r in good)),
        'connection_notes': c.get('connection_notes') or '[connection conditions not recorded]',
    }


def render(template, data):
    for _, key, spec, conversion in Formatter().parse(template):
        if key is not None and (key not in data or spec or conversion):
            raise ValueError(f'Unsupported template placeholder: {{{key}}}')
    return template.format_map(data)


def draft(c, rows):
    data = values(c, rows)
    templates = c.get('templates', {})
    return {
        'subject': render(templates.get('subject', SUBJECT), data),
        'body': render(templates.get('body', BODY), data),
        'to': c.get('profile', {}).get('provider_email', ''),
        'from': c['email']['from'],
    }
