import unittest

from lookup_cases import SeatIdLookupCases
import test_queries


class SeatIdLookupTests(SeatIdLookupCases, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_queries.SeatQueryTests.asyncSetUp
    asyncTearDown = test_queries.SeatQueryTests.asyncTearDown
