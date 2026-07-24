from a2a_dygrade_rl.agents.base_agent import BaseAgent


class ArbitratorAgent(BaseAgent):
    role = "arbitrator"

    @property
    def role_name(self) -> str:
        return self.role
