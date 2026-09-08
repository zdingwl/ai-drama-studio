from pathlib import Path

from pydantic import ValidationError

from app.projects.enums import ProjectType
from app.skills.models import RootSkillDefinition, RootSkillDetail, SkillManifest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SKILL_ROOT = _REPO_ROOT / "skills" / "projects"


class SkillRegistry:
    def __init__(self, skill_root: Path) -> None:
        self.skill_root = skill_root
        self._by_project_type: dict[ProjectType, RootSkillDefinition] = {}
        self._by_id: dict[str, RootSkillDefinition] = {}
        self._load()

    @classmethod
    def load_from(cls, skill_root: Path) -> "SkillRegistry":
        return cls(skill_root)

    def _load(self) -> None:
        if not self.skill_root.exists():
            raise RuntimeError(f"Skill 根目录不存在: {self.skill_root}")

        manifest_files = sorted(self.skill_root.glob("*/manifest.json"))
        if not manifest_files:
            raise RuntimeError(f"Skill 根目录没有 manifest: {self.skill_root}")

        for manifest_file in manifest_files:
            try:
                manifest = SkillManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(f"Skill manifest 无效: {manifest_file}: {exc}") from exc

            if manifest.id in self._by_id:
                raise RuntimeError(f"Skill id 重复: {manifest.id}")
            if manifest.project_type in self._by_project_type:
                raise RuntimeError(f"ProjectType 重复绑定 Root Skill: {manifest.project_type.value}")

            manual_file = self.skill_root / manifest.manual_path
            if not manual_file.is_file():
                raise RuntimeError(f"Skill 手册不存在: {manual_file}")

            self._by_id[manifest.id] = manifest
            self._by_project_type[manifest.project_type] = manifest

        expected = set(ProjectType)
        actual = set(self._by_project_type)
        if actual != expected:
            missing = sorted(item.value for item in expected - actual)
            extra = sorted(item.value for item in actual - expected)
            raise RuntimeError(f"Root Skill 集合不完整: missing={missing}, extra={extra}")

    def list(self) -> list[RootSkillDefinition]:
        return [self._by_project_type[project_type] for project_type in ProjectType]

    def get_by_project_type(self, project_type: ProjectType) -> RootSkillDefinition:
        return self._by_project_type[project_type]

    def get_by_id(self, skill_id: str) -> RootSkillDefinition | None:
        return self._by_id.get(skill_id)

    def get_bound_skill(self, *, project_type: ProjectType, skill_id: str, skill_version: str) -> RootSkillDefinition:
        skill = self.get_by_project_type(project_type)
        if skill.id != skill_id or skill.version != skill_version:
            raise RuntimeError(
                "项目绑定的 Root Skill 版本当前不可用: "
                f"project_type={project_type.value}, bound={skill_id}@{skill_version}, "
                f"available={skill.id}@{skill.version}"
            )
        return skill

    def detail(self, skill: RootSkillDefinition) -> RootSkillDetail:
        manual_file = self.skill_root / skill.manual_path
        return RootSkillDetail(**skill.model_dump(), manual=manual_file.read_text(encoding="utf-8"))


REGISTRY = SkillRegistry(_DEFAULT_SKILL_ROOT)


def list_root_skills() -> list[RootSkillDefinition]:
    return REGISTRY.list()


def get_root_skill(project_type: ProjectType) -> RootSkillDefinition:
    return REGISTRY.get_by_project_type(project_type)


def get_root_skill_by_id(skill_id: str) -> RootSkillDefinition | None:
    return REGISTRY.get_by_id(skill_id)


def get_bound_root_skill(*, project_type: ProjectType, skill_id: str, skill_version: str) -> RootSkillDefinition:
    return REGISTRY.get_bound_skill(
        project_type=project_type,
        skill_id=skill_id,
        skill_version=skill_version,
    )


def get_skill_detail(skill: RootSkillDefinition) -> RootSkillDetail:
    return REGISTRY.detail(skill)
