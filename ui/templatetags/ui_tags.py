from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from decimal import Decimal
import datetime

register = template.Library()


@register.inclusion_tag('ui/tags/status_badge.html')
def status_badge(status):
    """
    Renders a colored status badge based on the status value.
    """
    # Define color mappings
    color_map = {
        # Customer & Subscription statuses
        'active': 'success',
        'trialing': 'info',
        'suspended': 'danger',
        'cancelled': 'secondary',
        'past_due': 'warning',
        'unpaid': 'danger',
        'incomplete': 'warning',
        'incomplete_expired': 'secondary',
        'paused': 'warning',
        # Instance statuses
        'provisioning': 'info',
        'deprovisioned': 'secondary',
        # Invoice statuses
        'draft': 'secondary',
        'open': 'warning',
        'paid': 'success',
        'void': 'secondary',
        'uncollectible': 'danger',
    }

    badge_color = color_map.get(status, 'secondary')
    display_text = status.replace('_', ' ').title()

    return {
        'status': status,
        'badge_color': badge_color,
        'display_text': display_text,
    }


@register.filter
def money(value):
    """
    Format a number as currency in European format.
    Example: 9240.00 -> "9.240,00 €"
    """
    if value is None:
        return "0,00 €"

    try:
        value = Decimal(str(value))
        # Format with 2 decimal places
        formatted = f"{value:,.2f}"
        # Replace , with . for thousands and . with , for decimals (European format)
        formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{formatted} €"
    except (ValueError, TypeError):
        return "0,00 €"


@register.filter
def timesince_short(value):
    """
    Returns a short relative time string.
    Examples: "vor 8 Min.", "vor 2 Std.", "gestern", "12. Mai"
    """
    if not value:
        return ""

    now = timezone.now()

    # Make value timezone-aware if it isn't
    if timezone.is_naive(value):
        value = timezone.make_aware(value)

    diff = now - value

    if diff < datetime.timedelta(minutes=1):
        return "gerade eben"
    elif diff < datetime.timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"vor {minutes} Min."
    elif diff < datetime.timedelta(hours=24):
        hours = int(diff.total_seconds() / 3600)
        return f"vor {hours} Std."
    elif diff < datetime.timedelta(days=2):
        return "gestern"
    elif diff < datetime.timedelta(days=7):
        days = diff.days
        return f"vor {days} Tagen"
    else:
        # Format as "12. Mai" or with year if not current year
        if value.year == now.year:
            return value.strftime("%-d. %B")
        else:
            return value.strftime("%-d. %B %Y")


@register.filter
def mask_key(value):
    """
    Mask an API key showing only the prefix and last 4 characters.
    Example: "sk-1234567890abcdef" -> "sk-••••••••abcdef"
    """
    if not value or len(value) < 8:
        return value

    # Show first 3 characters (e.g., "sk-") and last 4
    prefix = value[:3]
    suffix = value[-4:]
    masked_length = len(value) - 7

    return f"{prefix}{'•' * masked_length}{suffix}"


@register.filter
def initials(value):
    """
    Get initials from a name or email.
    Example: "John Doe" -> "JD", "john@example.com" -> "J"
    """
    if not value:
        return "?"

    # If it's an email, take the part before @
    if '@' in value:
        value = value.split('@')[0]

    # Split by spaces and take first letter of each word
    parts = value.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1:
        return parts[0][0].upper()
    else:
        return "?"


@register.simple_tag
def active_nav(request, url_name):
    """
    Returns 'active' if the current URL matches the given URL name.
    Usage: <li class="{% active_nav request 'dashboard' %}">
    """
    if request.resolver_match and request.resolver_match.url_name == url_name:
        return 'active'
    return ''
