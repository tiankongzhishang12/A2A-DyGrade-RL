from a2a_dygrade_rl.agents.base_agent import BaseAgent


class StrongAgent(BaseAgent):
    role = "strong_scorer"

    @property
    def role_name(self) -> str:
        return self.role
