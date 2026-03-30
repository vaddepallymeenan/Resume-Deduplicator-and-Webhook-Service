"""
CLI entry-point for Resume Deduplication System
================================================
Usage:
  python main.py build   --corpus data/resumes.json  --model model.pkl
  python main.py check   --model model.pkl  --resume data/query.json
  python main.py demo
"""

import argparse
import json
import sys
import time
import logging
from pathlib import Path

from deduplicator import ResumeDuplicateDetector, parse_resume, Resume

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_corpus(path: str) -> list[Resume]:
    """Load resumes from a JSON file.
    Expected format: list of {"id": ..., "text": ...}
    """
    with open(path) as f:
        records = json.load(f)
    resumes = []
    for rec in records:
        r = parse_resume(rec["id"], rec["text"])
        resumes.append(r)
    return resumes


def print_result(result) -> None:
    print("\n" + "=" * 55)
    print(f"  Query ID      : {result.query_id}")
    print(f"  Match ID      : {result.match_id or '—'}")
    print(f"  Score         : {result.similarity_score:.4f}")
    print(f"  Is Duplicate  : {'✅ YES' if result.is_duplicate else '❌ NO'}")
    print(f"  Method        : {result.method}")
    if result.section_scores:
        print("  Section Scores:")
        for sec, sc in result.section_scores.items():
            bar = "█" * int(sc * 20)
            print(f"    {sec:<12}: {sc:.4f}  {bar}")
    print("=" * 55 + "\n")


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_build(args):
    print(f"Loading corpus from {args.corpus} …")
    resumes = load_corpus(args.corpus)
    print(f"  {len(resumes)} resumes loaded.")

    detector = ResumeDuplicateDetector(threshold=args.threshold)
    t0 = time.time()
    detector.add_resumes_bulk(resumes)
    elapsed = time.time() - t0
    print(f"  Indexed in {elapsed:.2f}s")
    detector.save(args.model)
    print(detector.stats())


def cmd_check(args):
    detector = ResumeDuplicateDetector.load(args.model)

    with open(args.resume) as f:
        rec = json.load(f)

    query = parse_resume(rec.get("id", "query"), rec["text"])
    result = detector.is_duplicate(query)
    print_result(result)


def cmd_demo(_args):
    """Run a self-contained demo with synthetic resumes."""
    print("\n🚀  Running built-in demo …\n")

    resumes_raw = [
        {
            "id": "r001",
            "text": (
                "John Doe  john.doe@email.com  +91-9876543210\n"
                "Summary: Experienced Python developer with 5 years in backend.\n"
                "Skills: Python, Django, REST APIs, PostgreSQL, Docker, AWS\n"
                "Experience: Software Engineer at TechCorp 2019-2024. Built microservices.\n"
                "Education: B.Tech Computer Science, IIT Delhi 2019"
            ),
        },
        {
            "id": "r002",
            "text": (
                "Jane Smith  jane.smith@gmail.com  +91-8765432109\n"
                "Summary: Data scientist specializing in NLP and ML models.\n"
                "Skills: Python, TensorFlow, PyTorch, scikit-learn, SQL, Spark\n"
                "Experience: Data Scientist at Analytics Inc 2020-2024. Built NLP pipelines.\n"
                "Education: M.Sc Statistics, IISc Bangalore 2020"
            ),
        },
        {
            "id": "r003",
            "text": (
                "Alice Johnson  alice.j@outlook.com  +91-7654321098\n"
                "Summary: Full-stack developer with React and Node.js expertise.\n"
                "Skills: JavaScript, React, Node.js, MongoDB, CSS, HTML\n"
                "Experience: Frontend Developer at WebWorks 2021-2024.\n"
                "Education: B.E. Information Technology, VIT 2021"
            ),
        },
    ]

    # Slightly modified duplicate of r001 — different email, updated skills
    duplicate_raw = {
        "id": "r001_dup",
        "text": (
            "John Doe  johndoe2024@gmail.com  +91-9876543210\n"
            "Summary: Experienced Python developer with 6 years in backend systems.\n"
            "Skills: Python, Django, FastAPI, REST APIs, PostgreSQL, Docker, AWS, Kubernetes\n"
            "Experience: Senior Software Engineer at TechCorp 2019-2024. Designed microservices.\n"
            "Education: B.Tech Computer Science, IIT Delhi 2019"
        ),
    }

    # Clearly different resume
    different_raw = {
        "id": "r999",
        "text": (
            "Carlos Rivera  carlos@hr.com  +91-6543210987\n"
            "Summary: HR Manager with 8 years of recruitment experience.\n"
            "Skills: Recruitment, Talent Acquisition, HRMS, Employee Relations\n"
            "Experience: HR Manager at PeopleFirst 2016-2024.\n"
            "Education: MBA Human Resources, XLRI Jamshedpur 2016"
        ),
    }

    detector = ResumeDuplicateDetector(threshold=0.75)
    resumes = [parse_resume(r["id"], r["text"]) for r in resumes_raw]
    detector.add_resumes_bulk(resumes)
    print(f"Indexed {len(resumes)} resumes.\n")

    print("─── Test 1: Checking duplicate of r001 (same phone, updated content) ───")
    dup = parse_resume(duplicate_raw["id"], duplicate_raw["text"])
    print_result(detector.is_duplicate(dup))

    print("─── Test 2: Checking a completely different resume ───")
    diff = parse_resume(different_raw["id"], different_raw["text"])
    print_result(detector.is_duplicate(diff))

    print("─── Test 3: Checking an exact copy of r002 ───")
    exact = parse_resume("r002_exact", resumes[1].raw_text)
    print_result(detector.is_duplicate(exact))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Resume Deduplication System")
    sub = parser.add_subparsers(dest="cmd")

    p_build = sub.add_parser("build", help="Index a corpus of resumes")
    p_build.add_argument("--corpus",    required=True, help="Path to resumes JSON")
    p_build.add_argument("--model",     default="model.pkl", help="Output model file")
    p_build.add_argument("--threshold", type=float, default=0.85)

    p_check = sub.add_parser("check", help="Check if a resume is a duplicate")
    p_check.add_argument("--model",  required=True)
    p_check.add_argument("--resume", required=True, help="Path to query resume JSON")

    sub.add_parser("demo", help="Run built-in demo with synthetic data")

    args = parser.parse_args()
    if args.cmd == "build":
        cmd_build(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "demo":
        cmd_demo(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
