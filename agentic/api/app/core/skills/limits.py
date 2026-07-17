from dataclasses import dataclass


@dataclass(frozen=True)
class SkillPackageLimits:
    archive_bytes: int = 50 * 1024 * 1024
    extracted_bytes: int = 100 * 1024 * 1024
    file_count: int = 256
    file_bytes: int = 10 * 1024 * 1024
    skill_md_bytes: int = 256 * 1024
    relative_path_chars: int = 240
