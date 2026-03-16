class AgentException(Exception):
    pass


class LLMException(AgentException):
    pass


class MCPException(AgentException):
    pass


class SkillException(AgentException):
    pass


class SkillNotFoundError(SkillException):
    pass


class SkillLoadError(SkillException):
    pass


class MCPConnectionError(MCPException):
    pass


class MCPToolNotFoundError(MCPException):
    pass
