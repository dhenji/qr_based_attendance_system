from core.exceptions import AppException, DatabaseException, DomainException


class StudentException(AppException):
    """Root umbrella for all student errors."""


class StudentDomainException(StudentException, DomainException):
    pass


class NotEnrolledException(StudentDomainException):
    """403 - student is not enrolled in the course for this session."""

    status_code: int = 403
    code: str = "not_enrolled"

    def __init__(self, student_id: int, course_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} is not enrolled in course {course_id}"
        )


class FaceNotEnrolledException(StudentDomainException):
    """403 - student has no face enrollment on record."""

    status_code: int = 403
    code: str = "face_not_enrolled"

    def __init__(self, student_id: int) -> None:
        super().__init__(message=f"Student {student_id} has no face enrollment")
