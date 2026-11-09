import unittest

from src.analytics.roles import agent_profile


class AgentProfileTests(unittest.TestCase):
    def test_dominant_role_and_three_most_played_agents(self):
        result = agent_profile(["Jett"] * 6 + ["Raze"] * 3 + ["KAY/O"] * 2 + ["Omen"])
        self.assertEqual(result["role"], "Duelist")
        self.assertEqual([agent["name"] for agent in result["top_agents"]], ["Jett", "Raze", "KAY/O"])
        self.assertEqual(result["role_maps"]["Initiator"], 2)

    def test_flex_uses_a_second_role_and_requires_five_classified_maps(self):
        self.assertEqual(agent_profile(["Jett"] * 3 + ["Omen"] * 3)["role"], "Flex")
        self.assertIsNone(agent_profile(["Jett"] * 4 + [None, "unknown"])["role"])
