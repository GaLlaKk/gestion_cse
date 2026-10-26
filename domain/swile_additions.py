from domain.normalization import (
    active_directory_keys,
    is_direction_position,
    normalize_matricule,
    normalize_name,
    split_full_name,
)


def build_additions(swile_users, active_directory_users, report_domain):
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
        if normalized_email.endswith(f".ext@{normalized_domain}"):
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
        if is_direction_position(user.get("Poste")):
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
