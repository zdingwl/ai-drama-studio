from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.skills.models import ArtifactType, Capability, SkillStepDefinition


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROFESSIONAL_SKILL_ROOT = _REPO_ROOT / "skills" / "professional"


class ProfessionalSkillManifest(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1200)
    when_to_use: tuple[str, ...]
    when_not_to_use: tuple[str, ...]
    required_inputs: tuple[ArtifactType, ...]
    optional_inputs: tuple[ArtifactType, ...] = ()
    readable_artifacts: tuple[ArtifactType, ...]
    required_capabilities: tuple[Capability, ...]
    manual_path: str = Field(min_length=1, max_length=240)
    steps: tuple[SkillStepDefinition, ...]
    fact_levels: tuple[str, ...] = ()
    provider_rules: tuple[str, ...]
    output_contracts: tuple[ArtifactType, ...]
    completion_criteria: tuple[str, ...]
    failure_policy: tuple[str, ...]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ProfessionalSkillManifest":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Professional Skill step id 不能重复")
        declared = set(self.required_capabilities)
        used = {capability for step in self.steps for capability in step.capabilities}
        missing = used - declared
        if missing:
            raise ValueError(
                f"Professional Skill step 使用了未声明 capability: {sorted(item.value for item in missing)}"
            )
        if not self.steps:
            raise ValueError("Professional Skill 必须至少包含一个执行步骤")
        if not self.provider_rules:
            raise ValueError("Professional Skill 必须包含 provider execution rules")
        return self


class ProfessionalSkillDetail(ProfessionalSkillManifest):
    manual: str


class ProfessionalSkillRegistry:
    def __init__(self, skill_root: Path) -> None:
        self.skill_root = skill_root
        self._by_id: dict[str, ProfessionalSkillManifest] = {}
        self._load()

    @classmethod
    def load_from(cls, skill_root: Path) -> "ProfessionalSkillRegistry":
        return cls(skill_root)

    def _load(self) -> None:
        if not self.skill_root.exists():
            raise RuntimeError(f"Professional Skill 根目录不存在: {self.skill_root}")
        manifest_files = sorted(self.skill_root.glob("*/manifest.json"))
        if not manifest_files:
            raise RuntimeError(f"Professional Skill 根目录没有 manifest: {self.skill_root}")
        for manifest_file in manifest_files:
            try:
                manifest = ProfessionalSkillManifest.model_validate_json(
                    manifest_file.read_text(encoding="utf-8")
                )
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(f"Professional Skill manifest 无效: {manifest_file}: {exc}") from exc
            if manifest.id in self._by_id:
                raise RuntimeError(f"Professional Skill id 重复: {manifest.id}")
            manual_file = self.skill_root / manifest.manual_path
            if not manual_file.is_file():
                raise RuntimeError(f"Professional Skill 手册不存在: {manual_file}")
            self._by_id[manifest.id] = manifest

    def list(self) -> list[ProfessionalSkillManifest]:
        return list(self._by_id.values())

    def get(self, skill_id: str) -> ProfessionalSkillManifest:
        skill = self._by_id.get(skill_id)
        if skill is None:
            raise RuntimeError(f"Professional Skill 不存在: {skill_id}")
        return skill

    def detail(self, skill_id: str) -> ProfessionalSkillDetail:
        skill = self.get(skill_id)
        manual_file = self.skill_root / skill.manual_path
        return ProfessionalSkillDetail(
            **skill.model_dump(),
            manual=manual_file.read_text(encoding="utf-8"),
        )


PROFESSIONAL_SKILLS = ProfessionalSkillRegistry(_DEFAULT_PROFESSIONAL_SKILL_ROOT)


def list_professional_skills() -> list[ProfessionalSkillManifest]:
    return PROFESSIONAL_SKILLS.list()


def get_professional_skill(skill_id: str) -> ProfessionalSkillManifest:
    return PROFESSIONAL_SKILLS.get(skill_id)


def get_professional_skill_detail(skill_id: str) -> ProfessionalSkillDetail:
    return PROFESSIONAL_SKILLS.detail(skill_id)
