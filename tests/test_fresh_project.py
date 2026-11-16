import time
import unittest

import views


class FreshProjectTests(unittest.TestCase):
    """The NEW chip must be short-lived and must not depend on navigation."""

    def setUp(self):
        import streamlit as st

        st.session_state.clear()

    def test_a_project_created_just_now_is_fresh(self):
        import streamlit as st

        st.session_state["new_project_flash"] = {"name": "DES run", "at": time.time()}
        self.assertEqual(views._fresh_project(), "DES run")

    def test_after_three_seconds_it_is_forgotten(self):
        import streamlit as st

        st.session_state["new_project_flash"] = {"name": "DES run",
                                                 "at": time.time() - 5}
        self.assertEqual(views._fresh_project(), "")
        self.assertNotIn("new_project_flash", st.session_state)

    def test_without_a_flash_nothing_is_fresh(self):
        self.assertEqual(views._fresh_project(), "")


if __name__ == "__main__":
    unittest.main()
