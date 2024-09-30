class AWSConfigError(Exception):
    pass


class AWSConfigNotFoundError(FileNotFoundError):
    pass


class SectionNotFoundError(AWSConfigError):
    pass
