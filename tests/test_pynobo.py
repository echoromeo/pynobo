import unittest

from pynobo import nobo

class TestValidation(unittest.TestCase):

    def test_is_valid_datetime(self):
        self.assertTrue(nobo.API.is_valid_datetime("202404041800"))
        self.assertFalse(nobo.API.is_valid_datetime("2024040418001"))
        self.assertFalse(nobo.API.is_valid_datetime("20240404180"))
        self.assertFalse(nobo.API.is_valid_datetime("invalid"))

    def test_time_is_quarter(self):
        self.assertTrue(nobo.API.time_is_quarter("00"))
        self.assertTrue(nobo.API.time_is_quarter("15"))
        self.assertTrue(nobo.API.time_is_quarter("30"))
        self.assertTrue(nobo.API.time_is_quarter("45"))
        self.assertFalse(nobo.API.time_is_quarter("01"))
        self.assertFalse(nobo.API.time_is_quarter("59"))

    def test_validate_temperature(self):
        nobo.API.validate_temperature("20")
        nobo.API.validate_temperature(20)
        nobo.API.validate_temperature(7)
        nobo.API.validate_temperature(30)
        with self.assertRaises(TypeError):
            nobo.API.validate_temperature(0.0)
        with self.assertRaisesRegex(ValueError, "must be digits"):
            nobo.API.validate_temperature("foo")
        with self.assertRaisesRegex(ValueError, "Min temperature is 7"):
            nobo.API.validate_temperature(6)
        with self.assertRaisesRegex(ValueError, "Max temperature is 30"):
            nobo.API.validate_temperature(31)

    def test_validate_week_profile(self):
        nobo.API.validate_week_profile(['00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000'])
        nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000','00000'])
        nobo.API.validate_week_profile(['00000','00001','00002','00004','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "must contain exactly 7 entries for midnight"):
            nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "must contain exactly 7 entries for midnight"):
            nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "invalid state"):
            nobo.API.validate_week_profile(['00003','00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "not in whole quarters"):
            nobo.API.validate_week_profile(['00000','01231','00000','00000','00000','00000','00000','00000'])

if __name__ == '__main__':
    unittest.main()
