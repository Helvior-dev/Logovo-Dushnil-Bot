"""Offline tests for Telegram bot state and startup checks."""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import main


class BotStateTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        main.active_duels.clear()
        main.active_votes.clear()

    async def test_stale_duel_button_cannot_accept_new_duel(self):
        chat_id = -100
        main.active_duels[chat_id] = {
            "challenger": 30, "target": 40, "message_id": 200,
        }
        query = SimpleNamespace(
            message=SimpleNamespace(chat_id=chat_id, message_id=100),
            data="duel_accept_10_20",
            from_user=SimpleNamespace(id=20),
            answer=AsyncMock(),
        )
        context = SimpleNamespace(bot=SimpleNamespace(get_chat_member=AsyncMock()))

        await main.duel_callback(SimpleNamespace(callback_query=query), context)

        query.answer.assert_awaited_once_with("Эта дуэль уже закончилась.", show_alert=True)
        self.assertEqual(main.active_duels[chat_id]["message_id"], 200)
        context.bot.get_chat_member.assert_not_awaited()

    async def test_old_duel_timeout_does_not_cancel_new_duel(self):
        chat_id = -100
        main.active_duels[chat_id] = {
            "challenger": 30, "target": 40, "message_id": 200,
        }
        response = SimpleNamespace(message_id=100, edit_text=AsyncMock())
        with patch("main.asyncio.sleep", new_callable=AsyncMock):
            await main.duel_timeout(
                SimpleNamespace(), chat_id,
                SimpleNamespace(first_name="old challenger"),
                SimpleNamespace(first_name="old target"), response,
            )

        self.assertEqual(main.active_duels[chat_id]["message_id"], 200)
        response.edit_text.assert_not_awaited()

    async def test_stale_vote_button_cannot_change_new_vote(self):
        chat_id = -100
        main.active_votes[chat_id] = {
            "target_id": 40,
            "target_name": "current target",
            "voters_yes": {30},
            "voters_no": set(),
            "all_voters": {30},
            "message_id": 200,
        }
        query = SimpleNamespace(
            message=SimpleNamespace(chat_id=chat_id, message_id=100, reply_markup=None),
            data="vote_yes_20",
            from_user=SimpleNamespace(id=50),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )

        await main.vote_callback(SimpleNamespace(callback_query=query), SimpleNamespace())

        query.answer.assert_awaited_once_with("Это голосование уже закончилось.", show_alert=True)
        self.assertEqual(main.active_votes[chat_id]["all_voters"], {30})
        query.edit_message_text.assert_not_awaited()

    async def test_old_vote_timeout_does_not_end_new_vote(self):
        chat_id = -100
        main.active_votes[chat_id] = {
            "target_id": 40, "target_name": "current target",
            "voters_yes": {30}, "voters_no": set(), "all_voters": {30},
            "message_id": 200,
        }
        response = SimpleNamespace(message_id=100, edit_text=AsyncMock())
        with patch("main.asyncio.sleep", new_callable=AsyncMock):
            await main.vote_end(
                SimpleNamespace(), chat_id, SimpleNamespace(first_name="old target"), response,
            )

        self.assertEqual(main.active_votes[chat_id]["message_id"], 200)
        response.edit_text.assert_not_awaited()

    async def test_canceling_apology_timeout_cancels_previous_timer(self):
        timer = SimpleNamespace(done=Mock(return_value=False), cancel=Mock())
        context = SimpleNamespace(user_data={"timeout_task": timer})

        main.cancel_apology_timeout(context)

        timer.cancel.assert_called_once_with()
        self.assertNotIn("timeout_task", context.user_data)

    async def test_raketka_in_another_chat_does_not_consume_apology(self):
        timer = SimpleNamespace(done=Mock(return_value=False), cancel=Mock())
        context = SimpleNamespace(user_data={
            "timeout_task": timer,
            "awaiting_apology": True,
            "apology_chat_id": -100,
        })
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1),
            chat_id=-200,
        )
        update = SimpleNamespace(message=message)

        with patch("main.random.choices", return_value=["none"]), \
             patch("main.reply_and_delete", new_callable=AsyncMock) as reply:
            await main.raketka(update, context)

        self.assertTrue(context.user_data["awaiting_apology"])
        self.assertEqual(context.user_data["apology_chat_id"], -100)
        timer.cancel.assert_not_called()
        reply.assert_awaited_once()

    async def test_old_apology_timeout_does_not_affect_new_state(self):
        context = SimpleNamespace(user_data={
            "timeout_task": object(),
            "awaiting_apology": True,
            "apology_chat_id": -200,
        })
        update = SimpleNamespace(message=SimpleNamespace(chat_id=-100, from_user=SimpleNamespace(id=1)))
        with patch("main.asyncio.sleep", new_callable=AsyncMock), \
             patch("main.try_mute", new_callable=AsyncMock) as try_mute:
            await main.timeout_check(update, context)

        try_mute.assert_not_awaited()
        self.assertTrue(context.user_data["awaiting_apology"])

    async def test_startup_fails_clearly_without_bot_token(self):
        with patch.dict(os.environ, {"BOT_TOKEN": ""}), \
             patch("main.Application.builder") as builder:
            with self.assertRaisesRegex(SystemExit, "BOT_TOKEN is not set"):
                main.main()
        builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
