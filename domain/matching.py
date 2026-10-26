from domain.normalization import (
    active_directory_keys,
    normalize_name,
    normalize_matricule,
)


def compare_users(swile_users, active_directory_users):
    active_directory_keys_by_type = {
        "email": set(),
        "matricule": set(),
        "name": set(),
    }
    for user in active_directory_users:
        for key_type, key in active_directory_keys(user).items():
            if key:
                active_directory_keys_by_type[key_type].add(key)

    found_users = []
    not_found_users = []
    for user in swile_users:
        user_keys = {
            "email": (user.get("Email") or "").strip().casefold(),
            "matricule": normalize_matricule(user.get("Matricule") or ""),
            "name": normalize_name(
                f"{user.get('Prénom') or ''}{user.get('Nom') or ''}"
            ),
        }
        if any(
            key and key in active_directory_keys_by_type[key_type]
            for key_type, key in user_keys.items()
        ):
            found_users.append(user)
        else:
            not_found_users.append(user)

    return found_users, not_found_users
