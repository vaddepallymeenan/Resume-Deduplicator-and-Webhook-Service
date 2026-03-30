"""
Test cases for Resume Deduplication System
"""

import pytest
from src.deduplicator import (
    ResumeDuplicateDetector,
    parse_resume,
    normalize_text,
    extract_shingles,
    build_minhash,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RESUME_1 = """
John Doe  john.doe@email.com  +91-9876543210
Summary: Experienced Python developer with 5 years in backend.
Skills: Python, Django, REST APIs, PostgreSQL, Docker, AWS
Experience: Software Engineer at TechCorp 2019-2024. Built microservices.
Education: B.Tech Computer Science, IIT Delhi 2019
"""

RESUME_2 = """
Jane Smith  jane.smith@gmail.com  +91-8765432109
Summary: Data scientist specializing in NLP and ML models.
Skills: Python, TensorFlow, PyTorch, scikit-learn, SQL, Spark
Experience: Data Scientist at Analytics Inc 2020-2024. Built NLP pipelines.
Education: M.Sc Statistics, IISc Bangalore 2020
"""

# Duplicate of RESUME_1: different email, updated skills/title
RESUME_1_DUP = """
John Doe  johndoe.new@gmail.com  +91-9876543210
Summary: Experienced Python developer with 6 years in backend systems.
Skills: Python, Django, FastAPI, REST APIs, PostgreSQL, Docker, AWS, Kubernetes
Experience: Senior Software Engineer at TechCorp 2019-2025. Designed microservices.
Education: B.Tech Computer Science, IIT Delhi 2019
"""

RESUME_DIFFERENT = """
Carlos Rivera  carlos@hr.com  +91-6543210987
Summary: HR Manager with 8 years of recruitment experience.
Skills: Recruitment, Talent Acquisition, HRMS, Employee Relations
Experience: HR Manager at PeopleFirst 2016-2024.
Education: MBA Human Resources, XLRI Jamshedpur 2016
"""


@pytest.fixture
def detector():
    d = ResumeDuplicateDetector(threshold=0.75)
    d.add_resumes_bulk([
        parse_resume("r001", RESUME_1),
        parse_resume("r002", RESUME_2),
    ])
    return d


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestTextUtils:
    def test_normalize_text_lowercase(self):
        assert normalize_text("Hello WORLD") == "hello world"

    def test_normalize_text_punctuation(self):
        result = normalize_text("Python, Django; REST-APIs")
        assert "," not in result
        assert ";" not in result

    def test_extract_shingles_length(self):
        shingles = extract_shingles("python django rest api", k=2)
        assert len(shingles) > 0

    def test_minhash_returns_object(self):
        m = build_minhash("python developer backend")
        assert m is not None


class TestParsing:
    def test_parse_email(self):
        r = parse_resume("x", RESUME_1)
        assert r.email == "john.doe@email.com"

    def test_parse_phone(self):
        r = parse_resume("x", RESUME_1)
        assert "9876543210" in r.phone

    def test_parse_skills(self):
        r = parse_resume("x", RESUME_1)
        assert "python" in r.skills

    def test_parse_minhash_created(self):
        r = parse_resume("x", RESUME_1)
        assert r.minhash is not None


class TestExactMatch:
    def test_same_phone_is_duplicate(self, detector):
        # RESUME_1_DUP has the same phone as RESUME_1
        dup = parse_resume("q", RESUME_1_DUP)
        result = detector.is_duplicate(dup)
        assert result.is_duplicate is True
        assert result.method == "exact_phone"

    def test_same_email_is_duplicate(self, detector):
        same_email = RESUME_1.replace(
            "john.doe@email.com", "john.doe@email.com"  # identical email
        )
        q = parse_resume("q2", same_email)
        result = detector.is_duplicate(q)
        assert result.is_duplicate is True


class TestSimilarityMatch:
    def test_exact_copy_is_duplicate(self, detector):
        exact = parse_resume("q_exact", RESUME_2)
        # Change the email/phone so stage-1 won't fire
        exact.email = "completely.different@test.com"
        exact.phone = "+91-0000000000"
        result = detector.is_duplicate(exact)
        assert result.is_duplicate is True
        assert result.similarity_score > 0.9

    def test_completely_different_is_not_duplicate(self, detector):
        diff = parse_resume("q_diff", RESUME_DIFFERENT)
        result = detector.is_duplicate(diff)
        assert result.is_duplicate is False


class TestBulkIngestion:
    def test_bulk_add(self):
        d = ResumeDuplicateDetector(threshold=0.8)
        resumes = [parse_resume(f"r{i}", RESUME_1 + f" id={i}") for i in range(50)]
        d.add_resumes_bulk(resumes)
        assert d.stats()["indexed_resumes"] == 50

    def test_duplicate_id_skipped(self, detector):
        before = detector.stats()["indexed_resumes"]
        detector.add_resume(parse_resume("r001", RESUME_1))  # same ID
        assert detector.stats()["indexed_resumes"] == before


class TestResultStructure:
    def test_result_has_all_fields(self, detector):
        q = parse_resume("q", RESUME_DIFFERENT)
        result = detector.is_duplicate(q)
        assert hasattr(result, "query_id")
        assert hasattr(result, "match_id")
        assert hasattr(result, "similarity_score")
        assert hasattr(result, "is_duplicate")
        assert hasattr(result, "method")

    def test_score_in_range(self, detector):
        q = parse_resume("q", RESUME_1_DUP)
        result = detector.is_duplicate(q)
        assert 0.0 <= result.similarity_score <= 1.0
