import re
import unicodedata

DIRECTION_TITLES = {
    "ceo",
    "coo",
    "dg",
    "dga",
    "pdg",
    "directeur",
    "directrice",
    "directreur",
    "direction",
    "president",
    "presidente",
}


def remove_diacritics(value):
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_matricule(value):
    return "".join(
        character
        for character in remove_diacritics(value.strip())
        if not character.isspace() and character != "-"
    )


def normalize_name(value):
    return "".join(
        character
        for character in remove_diacritics(value.strip())
        if character.isalnum()
    )


def active_directory_keys(user):
    email = (user.get("Email") or "").strip().casefold()
    full_name = (user.get("Nom") or "").strip()
    matricule = normalize_matricule(user.get("Identifiant") or "")

    return {
        "email": email,
        "matricule": matricule,
        "name": normalize_name(full_name),
    }


def is_direction_position(job_title):
    title_tokens = set(
        re.findall(r"[a-z0-9]+", remove_diacritics(job_title or ""))
    )
    return bool(title_tokens & DIRECTION_TITLES)


def split_full_name(full_name):
    name_parts = (full_name or "").strip().split(maxsplit=1)
    if len(name_parts) < 2:
        return None
    return name_parts[0], name_parts[1]
