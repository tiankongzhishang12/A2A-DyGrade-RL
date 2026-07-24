from a2a_dygrade_rl.agents.base_agent import BaseAgent


class EvidenceAgent(BaseAgent):
    role = "evidence_verifier"

    @property
    def role_name(self) -> str:
        return self.role
