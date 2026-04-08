"""Interview phase for clarifying questions with users during planning."""
from dataclasses import dataclass


@dataclass
class InterviewQuestion:
    """A question asked during the interview phase."""
    question: str
    answer: str | None = None
    asked_at: str | None = None
    answered_at: str | None = None


class InterviewPhase:
    """
    Phase for clarifying questions with user during planning.
    
    This allows the planner to ask clarifying questions before
    generating a complete plan.
    """

    def __init__(self):
        self.questions: list[InterviewQuestion] = []
        self.answers: dict[str, str] = {}
        self.feedback: list[str] = []

    def add_question(self, question: str) -> InterviewQuestion:
        """
        Add a new question to ask the user.
        
        Args:
            question: The question to ask
            
        Returns:
            The created InterviewQuestion object
        """
        from datetime import datetime
        q = InterviewQuestion(
            question=question,
            asked_at=datetime.now().isoformat()
        )
        self.questions.append(q)
        return q

    def add_answer(self, question: str, answer: str) -> None:
        """
        Record an answer to a question.
        
        Args:
            question: The question being answered
            answer: The user's answer
        """
        from datetime import datetime
        self.answers[question] = answer
        for q in self.questions:
            if q.question == question and q.answer is None:
                q.answer = answer
                q.answered_at = datetime.now().isoformat()
                break

    def check_understanding(self, question: str) -> str:
        """
        Check understanding of a specific topic/question.
        
        This is used during planning to verify understanding
        before proceeding.
        
        Args:
            question: The question or topic to check
            
        Returns:
            The question for clarification
        """
        return question

    def add_user_feedback(self, feedback: str) -> None:
        """
        Record user feedback for improving plan.
        
        Args:
            feedback: User's feedback on the plan
        """
        self.feedback.append(feedback)

    def get_pending_questions(self) -> list[str]:
        """
        Get list of questions that haven't been answered yet.
        
        Returns:
            List of unanswered questions
        """
        return [q.question for q in self.questions if q.answer is None]

    def get_answered_questions(self) -> list[dict[str, str]]:
        """
        Get list of answered questions with their answers.
        
        Returns:
            List of dicts with 'question' and 'answer' keys
        """
        return [
            {"question": q.question, "answer": q.answer}
            for q in self.questions
            if q.answer is not None
        ]

    def is_complete(self) -> bool:
        """
        Check if all questions have been answered.
        
        Returns:
            True if all questions are answered
        """
        return len(self.get_pending_questions()) == 0

    def clear(self) -> None:
        """Clear all questions and answers."""
        self.questions.clear()
        self.answers.clear()
        self.feedback.clear()

    def to_dict(self) -> dict:
        """Export interview state as dictionary."""
        return {
            "questions": [
                {
                    "question": q.question,
                    "answer": q.answer,
                    "asked_at": q.asked_at,
                    "answered_at": q.answered_at
                }
                for q in self.questions
            ],
            "pending_count": len(self.get_pending_questions()),
            "feedback": self.feedback
        }
