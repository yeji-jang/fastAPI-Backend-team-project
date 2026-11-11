"""실제 DB 접속 없이 get_db의 정상·실패 시 세션 처리를 검사한다."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from asyncticket.shared.core.database import get_db


class DatabaseSessionTests(unittest.IsolatedAsyncioTestCase):
    def prepare(self):
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        return session, context

    async def test_success_commits_only_after_consumer_finishes(self):
        session, context = self.prepare()
        with patch('asyncticket.shared.core.database.AsyncSessionLocal', return_value=context):
            dependency = get_db()
            self.assertIs(await anext(dependency), session)
            session.commit.assert_not_awaited()
            with self.assertRaises(StopAsyncIteration):
                await anext(dependency)
        session.commit.assert_awaited_once_with()
        session.rollback.assert_not_awaited()
        context.__aexit__.assert_awaited_once()

    async def test_consumer_failure_rolls_back_and_propagates(self):
        session, context = self.prepare()
        failure = RuntimeError('consumer failed')
        with patch('asyncticket.shared.core.database.AsyncSessionLocal', return_value=context):
            dependency = get_db()
            await anext(dependency)
            with self.assertRaises(RuntimeError) as raised:
                await dependency.athrow(failure)
        self.assertIs(raised.exception, failure)
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once_with()
        context.__aexit__.assert_awaited_once()

    async def test_commit_failure_rolls_back_and_propagates(self):
        session, context = self.prepare()
        failure = RuntimeError('commit failed')
        session.commit.side_effect = failure
        with patch('asyncticket.shared.core.database.AsyncSessionLocal', return_value=context):
            dependency = get_db()
            await anext(dependency)
            with self.assertRaises(RuntimeError) as raised:
                await anext(dependency)
        self.assertIs(raised.exception, failure)
        session.commit.assert_awaited_once_with()
        session.rollback.assert_awaited_once_with()
        context.__aexit__.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
