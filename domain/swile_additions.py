import re

from domain.normalization import (
    DIRECTION_TITLES,
    active_directory_keys,
    normalize_matricule,
    normalize_name,
    remove_diacritics,
    split_full_name,
)

DEFAULT_ADDITION_FILTERS = {
    "email": {
        "default_value": "inclure",
        "rules": [
            {"patterns": [[".ext@"]], "value": "exclure"},
        ],
    },
    "poste": {
        "default_value": "inclure",
        "rules": [
            {
                "patterns": [[token] for token in sorted(DIRECTION_TITLES)],
                "value": "exclure",
            },
        ],
    },
}


def build_additions(
    swile_users, active_directory_users, report_domain, filters=None
):
    """Prépare les ajouts Swile et compte les exclusions métier appliquées."""
    filters = filters or DEFAULT_ADDITION_FILTERS
    existing_keys = {"email": set(), "matricule": set(), "name": set()}
    for user in swile_users:
        email = (user.get("Email") or "").strip().casefold()
        matricule = normalize_matricule(user.get("Matricule") or "")
        name = normalize_name(
            f"{user.get('Prénom') or ''}{user.get('Nom') or ''}"
        )
        if email:
            existing_keys["email"].add(email)
        if matricule:
            existing_keys["matricule"].add(matricule)
        if name:
            existing_keys["name"].add(name)

    additions = []
    ignored_additions = []
    excluded_management = 0
    excluded_existing = 0
    excluded_invalid = 0
    excluded_external = 0
    seen_emails = set()
    normalized_domain = report_domain.lstrip("@").casefold()

    for user in active_directory_users:
        email = (user.get("Email") or "").strip()
        normalized_email = email.casefold()
        if not normalized_email.endswith(f"@{normalized_domain}"):
            continue
        email_filter = resolve_filter_value(normalized_email, filters["email"])
        if email_filter == "exclure":
            excluded_external += 1
            continue
        name_parts = split_full_name(user.get("Nom"))
        if not email or name_parts is None:
            excluded_invalid += 1
            continue
        if normalized_email in seen_emails:
            continue
        seen_emails.add(normalized_email)

        first_name, last_name = name_parts
        keys = active_directory_keys(user)
        name_key = normalize_name(f"{first_name}{last_name}")
        if any(
            (
                keys["email"] and keys["email"] in existing_keys["email"],
                keys["matricule"]
                and keys["matricule"] in existing_keys["matricule"],
                name_key and name_key in existing_keys["name"],
            )
        ):
            excluded_existing += 1
            continue

        addition = {
            "Prénom": first_name,
            "Nom": last_name,
            "Email": email,
            "Matricule": (user.get("Identifiant") or "").strip(),
        }
        job_title_filter = resolve_filter_value(
            user.get("Poste") or "", filters["poste"], whole_words=True
        )
        if job_title_filter == "exclure":
            excluded_management += 1
            ignored_additions.append(addition)
        else:
            additions.append(addition)

    return (
        additions,
        ignored_additions,
        excluded_management,
        excluded_existing,
        excluded_invalid,
        excluded_external,
    )


def resolve_filter_value(value, filter_config, whole_words=False):
    """Renvoie la valeur de la première règle correspondant au texte."""
    normalized_value = remove_diacritics(value.strip())
    for rule in filter_config["rules"]:
        for pattern in rule["patterns"]:
            if all(
                _filter_term_matches(
                    term, normalized_value, whole_words=whole_words
                )
                for term in pattern
            ):
                return rule["value"]
    return filter_config["default_value"]


def _filter_term_matches(term, value, whole_words=False):
    normalized_term = remove_diacritics(term.strip())
    if not whole_words:
        return normalized_term in value
    title_tokens = set(re.findall(r"[a-z0-9]+", value))
    term_tokens = re.findall(r"[a-z0-9]+", normalized_term)
    return bool(term_tokens) and all(token in title_tokens for token in term_tokens)
