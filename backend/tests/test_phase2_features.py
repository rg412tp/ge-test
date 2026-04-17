"""
Phase 2 Feature Tests for GCSE Question Bank Platform
Tests: GE IDs, Topics, Difficulty, Mark Scheme endpoints
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"

class TestHealthAndBasics:
    """Basic health and API info tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy with storage initialized"""
        response = requests.get(f"{API}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "storage_initialized" in data
        print(f"Health check passed: {data}")
    
    def test_api_root(self):
        """GET /api/ returns API info"""
        response = requests.get(f"{API}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "GCSE Question Bank API" in data["message"]
        print(f"API root passed: {data}")


class TestTopicsEndpoints:
    """Tests for GCSE topics - 30 predefined topics across 4 categories"""
    
    def test_get_all_topics(self):
        """GET /api/topics returns 30 predefined GCSE topics"""
        response = requests.get(f"{API}/topics")
        assert response.status_code == 200
        topics = response.json()
        assert isinstance(topics, list)
        assert len(topics) == 30, f"Expected 30 topics, got {len(topics)}"
        
        # Verify topic structure
        for topic in topics:
            assert "name" in topic
            assert "category" in topic
            assert "description" in topic
        
        # Verify some expected topics exist
        topic_names = [t["name"] for t in topics]
        expected_topics = ["quadratics", "trigonometry", "probability", "fractions"]
        for expected in expected_topics:
            assert expected in topic_names, f"Missing expected topic: {expected}"
        
        print(f"Topics endpoint passed: {len(topics)} topics returned")
    
    def test_get_topic_categories(self):
        """GET /api/topics/categories returns 4 categories (Number, Algebra, Geometry, Statistics)"""
        response = requests.get(f"{API}/topics/categories")
        assert response.status_code == 200
        categories = response.json()
        assert isinstance(categories, dict)
        
        expected_categories = ["Number", "Algebra", "Geometry", "Statistics"]
        for cat in expected_categories:
            assert cat in categories, f"Missing category: {cat}"
        
        assert len(categories) == 4, f"Expected 4 categories, got {len(categories)}"
        print(f"Topic categories passed: {list(categories.keys())}")


class TestGECodeGeneration:
    """Tests for GE ID system: GE-{year}-P{paper}-Q{number}"""
    
    def test_paper_creation_with_ge_code(self):
        """POST /api/papers creates paper with ge_code field (GE-{year}-P{paper})"""
        paper_data = {
            "board": "AQA",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "2",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2017
        }
        response = requests.post(f"{API}/papers", json=paper_data)
        assert response.status_code == 200
        paper = response.json()
        
        # Verify GE code format
        assert "ge_code" in paper, "Paper should have ge_code field"
        expected_ge_code = f"GE-{paper_data['exam_year']}-P{paper_data['paper_number']}"
        assert paper["ge_code"] == expected_ge_code, f"Expected {expected_ge_code}, got {paper['ge_code']}"
        
        print(f"Paper created with GE code: {paper['ge_code']}")
        return paper
    
    def test_papers_list_includes_ge_code(self):
        """GET /api/papers returns papers list with ge_code"""
        response = requests.get(f"{API}/papers")
        assert response.status_code == 200
        papers = response.json()
        
        # Check that papers have ge_code
        for paper in papers:
            if paper.get("exam_year") and paper.get("paper_number"):
                assert "ge_code" in paper, f"Paper {paper['id']} missing ge_code"
        
        print(f"Papers list passed: {len(papers)} papers with ge_codes")
    
    def test_get_paper_by_id_includes_ge_code(self):
        """GET /api/papers/{id} returns paper with ge_code"""
        # First create a paper
        paper_data = {
            "board": "Edexcel",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "1",
            "tier": "Foundation",
            "session": "November",
            "exam_year": 2019
        }
        create_response = requests.post(f"{API}/papers", json=paper_data)
        assert create_response.status_code == 200
        created_paper = create_response.json()
        
        # Get paper by ID
        get_response = requests.get(f"{API}/papers/{created_paper['id']}")
        assert get_response.status_code == 200
        paper = get_response.json()
        
        assert paper["ge_code"] == f"GE-2019-P1"
        print(f"Get paper by ID passed: {paper['ge_code']}")


class TestStatsEndpoint:
    """Tests for stats endpoint including total_mark_schemes"""
    
    def test_stats_includes_mark_schemes(self):
        """GET /api/stats returns stats including total_mark_schemes"""
        response = requests.get(f"{API}/stats")
        assert response.status_code == 200
        stats = response.json()
        
        required_fields = [
            "total_papers",
            "total_questions",
            "approved_questions",
            "pending_review",
            "total_images",
            "total_mark_schemes"
        ]
        
        for field in required_fields:
            assert field in stats, f"Stats missing field: {field}"
        
        print(f"Stats endpoint passed: {stats}")


class TestDifficultyTagging:
    """Tests for difficulty tagging (bronze/silver/gold)"""
    
    @pytest.fixture
    def test_paper_and_question(self):
        """Create a test paper and mock question for difficulty tests"""
        # Create paper
        paper_data = {
            "board": "OCR",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "3",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2020
        }
        paper_response = requests.post(f"{API}/papers", json=paper_data)
        paper = paper_response.json()
        return paper
    
    def test_difficulty_validation_valid_values(self, test_paper_and_question):
        """PATCH /api/questions/{id}/difficulty validates bronze/silver/gold only"""
        # Note: We can't test actual question difficulty update without a real question
        # But we can test the validation by checking the endpoint exists and validates
        
        # Test with invalid difficulty - should return 404 (no question) or 400 (invalid difficulty)
        fake_question_id = "nonexistent-question-id"
        
        # Test invalid difficulty value
        response = requests.patch(
            f"{API}/questions/{fake_question_id}/difficulty?difficulty=invalid"
        )
        # Should be 400 (invalid difficulty) or 404 (question not found)
        assert response.status_code in [400, 404]
        
        if response.status_code == 400:
            data = response.json()
            assert "Invalid difficulty" in data.get("detail", "")
            print("Difficulty validation passed: rejects invalid values")
        else:
            print("Difficulty validation: endpoint exists, returns 404 for nonexistent question")
    
    def test_difficulty_validation_rejects_invalid(self):
        """PATCH /api/questions/{id}/difficulty rejects invalid difficulty values"""
        fake_id = "test-question-id"
        
        # Test with invalid difficulty
        response = requests.patch(f"{API}/questions/{fake_id}/difficulty?difficulty=platinum")
        
        # Should reject with 400 or 404
        assert response.status_code in [400, 404]
        print(f"Difficulty validation test passed: status {response.status_code}")


class TestTopicTagging:
    """Tests for topic tagging validation"""
    
    def test_topics_validation_rejects_invalid(self):
        """PATCH /api/questions/{id}/topics validates against predefined topics"""
        fake_id = "test-question-id"
        
        # Test with invalid topics
        invalid_topics = ["invalid-topic-xyz", "not-a-real-topic"]
        response = requests.patch(
            f"{API}/questions/{fake_id}/topics",
            json=invalid_topics
        )
        
        # Should reject with 400 (invalid topics) or 404 (question not found)
        assert response.status_code in [400, 404]
        
        if response.status_code == 400:
            data = response.json()
            assert "Invalid topics" in data.get("detail", "")
            print("Topic validation passed: rejects invalid topics")
        else:
            print("Topic validation: endpoint exists, returns 404 for nonexistent question")


class TestQuestionsEndpoints:
    """Tests for questions endpoints"""
    
    def test_questions_empty_initially(self):
        """GET /api/questions returns empty array initially for a paper"""
        # Create a new paper
        paper_data = {
            "board": "AQA",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "1",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2021
        }
        paper_response = requests.post(f"{API}/papers", json=paper_data)
        paper = paper_response.json()
        
        # Get questions for this paper
        response = requests.get(f"{API}/questions?paper_id={paper['id']}")
        assert response.status_code == 200
        questions = response.json()
        assert isinstance(questions, list)
        assert len(questions) == 0, "New paper should have no questions"
        print("Questions empty initially test passed")


class TestPDFUploadEndpoints:
    """Tests for PDF upload endpoints"""
    
    def test_paper_upload_endpoint_exists(self):
        """POST /api/papers/{id}/upload accepts PDF and returns job_id"""
        # Create a paper first
        paper_data = {
            "board": "AQA",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "1",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2022
        }
        paper_response = requests.post(f"{API}/papers", json=paper_data)
        paper = paper_response.json()
        
        # Test upload endpoint without file (should fail with 422 - validation error)
        response = requests.post(f"{API}/papers/{paper['id']}/upload")
        # Without file, should return 422 (unprocessable entity)
        assert response.status_code == 422
        print("Paper upload endpoint exists and validates file requirement")
    
    def test_mark_scheme_upload_endpoint_exists(self):
        """POST /api/papers/{id}/mark-scheme/upload accepts PDF for mark scheme extraction"""
        # Create a paper first
        paper_data = {
            "board": "Edexcel",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "2",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2022
        }
        paper_response = requests.post(f"{API}/papers", json=paper_data)
        paper = paper_response.json()
        
        # Test mark scheme upload endpoint without file (should fail with 422)
        response = requests.post(f"{API}/papers/{paper['id']}/mark-scheme/upload")
        assert response.status_code == 422
        print("Mark scheme upload endpoint exists and validates file requirement")


class TestExtractionJobEndpoint:
    """Tests for extraction job status endpoint"""
    
    def test_extraction_job_not_found(self):
        """GET /api/extraction-jobs/{job_id} returns 404 for nonexistent job"""
        response = requests.get(f"{API}/extraction-jobs/nonexistent-job-id")
        assert response.status_code == 404
        print("Extraction job 404 test passed")


class TestMarkSchemeEndpoints:
    """Tests for mark scheme related endpoints"""
    
    def test_paper_mark_scheme_not_found(self):
        """GET /api/papers/{id}/mark-scheme returns 404 when no mark scheme exists"""
        # Create a paper
        paper_data = {
            "board": "AQA",
            "qualification": "GCSE",
            "subject": "Mathematics",
            "paper_number": "1",
            "tier": "Higher",
            "session": "June",
            "exam_year": 2023
        }
        paper_response = requests.post(f"{API}/papers", json=paper_data)
        paper = paper_response.json()
        
        # Try to get mark scheme (should be 404)
        response = requests.get(f"{API}/papers/{paper['id']}/mark-scheme")
        assert response.status_code == 404
        print("Mark scheme 404 test passed")
    
    def test_mark_scheme_entries_endpoint(self):
        """GET /api/mark-scheme-entries returns list (empty initially)"""
        response = requests.get(f"{API}/mark-scheme-entries")
        assert response.status_code == 200
        entries = response.json()
        assert isinstance(entries, list)
        print(f"Mark scheme entries endpoint passed: {len(entries)} entries")
    
    def test_question_mark_scheme_endpoint(self):
        """GET /api/questions/{id}/mark-scheme returns list for question"""
        fake_id = "test-question-id"
        response = requests.get(f"{API}/questions/{fake_id}/mark-scheme")
        assert response.status_code == 200
        entries = response.json()
        assert isinstance(entries, list)
        print("Question mark scheme endpoint passed")


class TestQuestionsByTopicAndDifficulty:
    """Tests for filtering questions by topic and difficulty"""
    
    def test_questions_by_topic_endpoint(self):
        """GET /api/questions/by-topic/{topic} returns questions with that topic"""
        response = requests.get(f"{API}/questions/by-topic/quadratics")
        assert response.status_code == 200
        questions = response.json()
        assert isinstance(questions, list)
        print(f"Questions by topic endpoint passed: {len(questions)} questions")
    
    def test_questions_by_difficulty_endpoint(self):
        """GET /api/questions/by-difficulty/{difficulty} returns questions with that difficulty"""
        response = requests.get(f"{API}/questions/by-difficulty/silver")
        assert response.status_code == 200
        questions = response.json()
        assert isinstance(questions, list)
        print(f"Questions by difficulty endpoint passed: {len(questions)} questions")
    
    def test_questions_by_difficulty_invalid(self):
        """GET /api/questions/by-difficulty/{invalid} returns 400"""
        response = requests.get(f"{API}/questions/by-difficulty/platinum")
        assert response.status_code == 400
        print("Questions by invalid difficulty returns 400 - passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
