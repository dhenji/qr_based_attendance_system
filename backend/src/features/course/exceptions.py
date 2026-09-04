from core.exceptions import AppException, DatabaseException, DomainException


class CourseException(AppException):
    """Root umbrella for all course errors."""


class CourseDomainException(CourseException, DomainException):
    pass


class CourseDatabaseException(CourseException, DatabaseException):
    pass
