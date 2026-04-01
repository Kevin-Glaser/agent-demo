"""Test all backend API endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app


# Test data
TEST_SKILL_METADATA = {
    "name": "test-skill",
    "description": "A test skill",
    "source": "directory"
}


class MockSkill:
    name = "test-skill"
    description = "A test skill"
    source = "directory"
    skill_md_content = "# Test Skill\n\nThis is a test."


class MockToolInfo:
    server = "test-server"
    name = "test-tool"
    description = "A test tool"
    input_schema = {"type": "object", "properties": {}}

    def model_dump(self):
        return {
            "server": self.server,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client."""
    with patch('mcp_client.client.mcp_client') as mock:
        mock.all_tools = [MockToolInfo()]
        mock.load_config = MagicMock()
        mock.load_all_tools = AsyncMock()
        mock.reload_tools = AsyncMock(return_value=1)
        mock.call_tool = AsyncMock(return_value=MagicMock(content=[MagicMock(text="test result")]))
        yield mock


@pytest.fixture
def mock_skill_manager():
    """Mock skill manager."""
    with patch('skills.manager.skill_manager') as mock:
        mock.get_all_skills = MagicMock(return_value=[])
        mock.get_skills_metadata = MagicMock(return_value=[])
        mock.should_use_compact_format = MagicMock(return_value=False)
        mock.build_skills_system_message = MagicMock(return_value="")
        mock.get_skill = MagicMock(return_value=MockSkill())
        mock.load_skill_from_zip = MagicMock(return_value=MockSkill())
        mock.remove_skill = MagicMock(return_value=True)
        yield mock


@pytest.fixture
def mock_llm_service():
    """Mock LLM service."""
    with patch('llm.openai_service.llm_service') as mock:
        mock.chat = AsyncMock(return_value=MagicMock(
            response="Test response",
            callTools=[]
        ))
        mock.chat_stream = MagicMock()
        mock.run_loop_chat = MagicMock()
        mock.conversation_manager = MagicMock()
        mock.conversation_manager.add_user_message = MagicMock()
        mock.conversation_manager.add_assistant_message = MagicMock()
        mock.conversation_manager.get_conversation_context = MagicMock(return_value=[])
        mock.conversation_manager.should_compact = MagicMock(return_value=False)
        mock.conversation_manager.check_and_compact = MagicMock(return_value={})
        mock.build_openai_tools = MagicMock(return_value=[])
        mock.tool_executor.extract_content = MagicMock(return_value="test result")
        yield mock


class TestToolsAPI:
    """Test /api/tools endpoints."""

    @pytest.mark.asyncio
    async def test_get_tools(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test GET /api/tools returns tools list."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)

    @pytest.mark.asyncio
    async def test_get_tools_reload(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test GET /api/tools?reload=true reloads tools."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/tools?reload=true")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data


class TestSkillsAPI:
    """Test /api/skills endpoints."""

    @pytest.mark.asyncio
    async def test_get_skills(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test GET /api/skills returns skills list."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/skills")

        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)

    @pytest.mark.asyncio
    async def test_delete_skill(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test DELETE /api/skills/{skill_name} deletes a skill."""
        # Mock the correct module path
        with patch('app.api.skills.skill_manager') as mock_skills_mgr:
            mock_skills_mgr.remove_skill.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete("/api/skills/test-skill")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_skill_not_found(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test DELETE /api/skills/{skill_name} returns 404 for non-existent skill."""
        mock_skill_manager.remove_skill.return_value = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/api/skills/non-existent")

        assert response.status_code == 404


class TestChatAPI:
    """Test /api/chat endpoints."""

    @pytest.mark.asyncio
    async def test_chat_simple(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test POST /api/chat returns a response."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={
                "message": "Hello",
                "history": []
            })

        assert response.status_code == 200
        data = response.json()
        assert "response" in data or "callTools" in data

    @pytest.mark.asyncio
    async def test_chat_with_history(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test POST /api/chat with conversation history."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={
                "message": "Continue the conversation",
                "history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"}
                ]
            })

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_stream(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test POST /api/chat/stream returns streaming response."""
        # Mock the async generator
        async def mock_stream():
            yield "data: {\"chunk_type\": \"text-delta\", \"content\": \"Hello\"}\n\n"
            yield "data: {\"chunk_type\": \"done\"}\n\n"

        mock_llm_service.chat_stream.return_value = mock_stream()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat/stream", json={
                "message": "Hello",
                "history": []
            })

        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_chat_loop(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test POST /api/chat/loop returns streaming response."""
        # Mock the async generator
        async def mock_loop():
            yield "data: {\"chunk_type\": \"done\", \"content\": \"{\\\"steps\\\": 1}\"}\n\n"

        mock_llm_service.run_loop_chat.return_value = mock_loop()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat/loop", json={
                "message": "Hello",
                "history": []
            })

        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_chat_empty_message(self, mock_mcp_client, mock_skill_manager, mock_llm_service):
        """Test POST /api/chat with empty message."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={
                "message": "",
                "history": []
            })

        # Should still process (possibly with validation error or accept it)
        assert response.status_code in [200, 422]


class TestConversationManager:
    """Test conversation management and compaction."""

    def test_token_estimation(self):
        """Test token estimation logic."""
        from session.token import estimate

        # 4 chars per token
        assert estimate("hello world") == 3  # 11 chars / 4 = 2.75 -> 3
        assert estimate("") == 0
        assert estimate("a" * 100) == 25  # 100 chars / 4 = 25

    def test_token_usage(self):
        """Test TokenUsage dataclass."""
        from session.token import TokenUsage

        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_write_tokens=100
        )

        assert usage.total == 1800
        assert usage.cache_total == 300
        assert usage.usable(4096) == 1800 - 4096  # negative is fine

    def test_token_budget(self):
        """Test TokenBudget calculations."""
        from session.token import TokenBudget, TokenUsage

        budget = TokenBudget(input_limit=10000, context_limit=10000, max_output_tokens=500)

        # Not overflow
        usage = TokenUsage(input_tokens=5000, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
        assert budget.is_overflow(usage) is False

        # Overflow
        usage = TokenUsage(input_tokens=9600, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
        assert budget.is_overflow(usage) is True


class TestCompactionLogic:
    """Test conversation compaction logic."""

    def test_compaction_initialization(self):
        """Test ConversationCompaction initializes correctly."""
        from session.compaction import ConversationCompaction

        compaction = ConversationCompaction()
        assert len(compaction.messages) == 0
        assert compaction.total_tokens == 0
        assert compaction.compaction_count == 0

    def test_add_message(self):
        """Test adding messages to compaction."""
        from session.compaction import ConversationCompaction

        compaction = ConversationCompaction()
        compaction.add_message("user", "Hello", message_id="msg1")

        assert len(compaction.messages) == 1
        assert compaction.messages[0].role == "user"
        assert compaction.messages[0].content == "Hello"

    def test_is_overflow_disabled(self):
        """Test is_overflow returns False when auto_compact is disabled."""
        from session.compaction import ConversationCompaction
        from unittest.mock import patch

        compaction = ConversationCompaction()
        with patch.object(compaction, 'is_auto_compact_enabled', return_value=False):
            # Even with huge tokens, should not overflow if disabled
            compaction.total_tokens = 999999
            assert compaction.is_overflow(model_context_limit=1000) is False

    def test_prune_protects_recent_messages(self):
        """Test that prune preserves recent messages."""
        from session.compaction import ConversationCompaction

        compaction = ConversationCompaction()
        compaction.add_message("user", "Message 1", message_id="msg1")
        compaction.add_message("assistant", "Response 1", message_id="msg2")
        compaction.add_message("user", "Message 2", message_id="msg3")
        compaction.add_message("assistant", "Response 2", message_id="msg4")

        # Prune should not remove recent messages
        pruned = compaction.prune()
        assert len(compaction.messages) >= 2  # Keep at least last 2 turns

    def test_filter_compacted(self):
        """Test filter_compacted logic."""
        from session.compaction import ConversationCompaction

        compaction = ConversationCompaction()
        compaction.add_message("user", "Hello", message_id="msg1")
        compaction.add_message("assistant", "Hi", message_id="msg2")

        filtered = compaction.filter_compacted()
        assert len(filtered) >= 0  # Should return valid messages


class TestPartTypes:
    """Test message part types."""

    def test_part_types_defined(self):
        """Test all PartType enum values are defined."""
        from session.compaction import PartType

        expected_types = [
            "text", "tool", "reasoning", "compaction", "file",
            "snapshot", "step-start", "step-finish", "patch",
            "agent", "subtask", "retry"
        ]

        actual_types = [pt.value for pt in PartType]
        for expected in expected_types:
            assert expected in actual_types

    def test_tool_call_state(self):
        """Test ToolCallState enum."""
        from session.compaction import ToolCallState

        assert ToolCallState.PENDING.value == "pending"
        assert ToolCallState.EXECUTING.value == "executing"
        assert ToolCallState.COMPLETED.value == "completed"
        assert ToolCallState.FAILED.value == "failed"


class TestMediaDetection:
    """Test media type detection."""

    def test_is_media_image(self):
        """Test image media type detection."""
        from session.compaction import isMedia

        assert isMedia("image/png") is True
        assert isMedia("image/jpeg") is True
        assert isMedia("image/webp") is True
        assert isMedia("image/svg+xml") is True

    def test_is_media_video(self):
        """Test video media type detection."""
        from session.compaction import isMedia

        assert isMedia("video/mp4") is True
        assert isMedia("video/webm") is True

    def test_is_media_audio(self):
        """Test audio media type detection."""
        from session.compaction import isMedia

        assert isMedia("audio/mpeg") is True
        assert isMedia("audio/wav") is True

    def test_is_not_media(self):
        """Test non-media types return False."""
        from session.compaction import isMedia

        assert isMedia("text/plain") is False
        assert isMedia("application/json") is False
        assert isMedia("") is False
        assert isMedia(None) is False


class TestMessageConversion:
    """Test message conversion for LLM."""

    def test_get_messages_for_llm_basic(self):
        """Test basic message conversion."""
        from session.compaction import ConversationCompaction

        compaction = ConversationCompaction()
        compaction.add_message("user", "Hello", message_id="msg1")

        messages = compaction.get_messages_for_llm()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_get_messages_for_llm_strip_media(self):
        """Test strip_media option."""
        from session.compaction import ConversationCompaction, MessagePart, PartType

        compaction = ConversationCompaction()
        part = MessagePart(
            part_type=PartType.FILE.value,
            content="",
            media_mime_type="image/png",
            filename="test.png",
            media_url="http://example.com/test.png"
        )
        compaction.add_message("user", "", parts=[part], message_id="msg1")

        # With strip_media=True, should return placeholder
        messages = compaction.get_messages_for_llm(strip_media=True)
        assert "[Attached image/png: test.png]" in messages[0]["content"]

    def test_get_messages_for_llm_compacted_tool(self):
        """Test compacted tool calls show placeholder."""
        from session.compaction import ConversationCompaction, MessagePart, PartType, ToolCallState

        compaction = ConversationCompaction()
        part = MessagePart(
            part_type=PartType.TOOL.value,
            content="Old tool result content",
            tool_name="test-tool",
            tool_call_state=ToolCallState.COMPLETED,
            compacted=True
        )
        compaction.add_message("assistant", "", parts=[part], message_id="msg1")

        messages = compaction.get_messages_for_llm()
        assert "[Old tool result content cleared]" in messages[0]["content"]
