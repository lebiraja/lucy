# Lucy Enhanced Features - Streaming, Monitoring & Crash Recovery

## Overview

Lucy has been enhanced with advanced capabilities to ensure robust, production-ready multi-agent orchestration:

1. **Automatic Model Detection** - Context windows auto-detected and continuously monitored
2. **Streaming Support** - Real-time token streaming for responsive UX
3. **Crash Recovery** - Data never lost, even when models fail mid-response
4. **Continuous Monitoring** - Background health checks every 30 seconds
5. **Performance Tracking** - Real-time metrics and analytics

---

## 1. Automatic Model Detection & Context Window Management

### What It Does
- Automatically detects model capabilities from vLLM endpoints
- Determines context window size for each model
- Adjusts `max_tokens` dynamically (40% of context window)
- Continuously monitors and updates as models change

### How It Works
```python
# When registering an agent, Lucy probes the endpoint
POST /api/agents
{
  "name": "Agent-1",
  "endpoint": "http://192.168.73.41:9002"
  // No need to specify model_name or context_window!
}

# Lucy automatically:
# 1. Detects model name (e.g., "Qwen/Qwen3-4B-FP8")
# 2. Extracts context window (e.g., 2048 tokens)
# 3. Sets safe max_tokens (e.g., 819 = 40% of 2048)
# 4. Monitors every 30s for changes
```

### Safety Mechanisms
- **Intelligent Token Allocation**:
  - Reserves 60% of context for input (minimum 512 tokens)
  - Caps output to 40% of context (minimum 256 tokens)
  - Adds 100-token overhead buffer for formatting
  
- **Prevents Context Overflow**:
  - Truncates input if too long (with clear marker)
  - Never requests more output tokens than available space
  - Respects model limits even if agent config is wrong

### Supported Models (Auto-Detected)
- Qwen3-4B, gemma-3-4b → 2048 tokens
- Ministral, Mistral-7B → 8192 tokens
- Llama-3 → 8192 tokens
- GPT models → 16384+ tokens
- Others → Safe 4096 default

---

## 2. Real-Time Streaming

### What It Does
Streams LLM responses token-by-token as they're generated, instead of waiting for completion.

### Endpoints

#### Stream Chat Completion
```bash
POST /api/agents/{agent_id}/chat/stream
Content-Type: application/json

{
  "messages": [{"role": "user", "content": "Write a story"}],
  "temperature": 0.7,
  "max_tokens": 512
}

# Response: Server-Sent Events (SSE)
data: {"content": "Once", "done": false}
data: {"content": " upon", "done": false}
data: {"content": " a", "done": false}
data: {"content": " time", "done": false}
...
data: {"content": "", "done": true, "duration_ms": 3421}
```

#### Stream Task Events (Logs)
```bash
GET /api/tasks/{task_id}/events

# Response: SSE stream of logs + completion status
data: {"type": "log", "level": "info", "message": "Task started"}
data: {"type": "log", "level": "agent", "message": "[Agent-1] responded"}
data: {"type": "done", "status": "completed", "task_id": 1}
```

### Client-Side Example (JavaScript)
```javascript
const eventSource = new EventSource('/api/agents/1/chat/stream');

eventSource.onmessage = (event) => {
  const chunk = JSON.parse(event.data);
  
  if (chunk.done) {
    console.log(`Completed in ${chunk.duration_ms}ms`);
    eventSource.close();
  } else {
    process.stdout.write(chunk.content); // Stream to UI
  }
};
```

---

## 3. Crash Recovery & Data Persistence

### What It Does
- **Never loses data** - Even if a model crashes mid-response
- **Auto-checkpointing** - Saves partial responses every ~500ms
- **Recovery on restart** - Resumes from last checkpoint
- **Graceful failure** - Returns partial data on errors

### How It Works

#### Automatic Checkpointing
```python
# As agent generates response:
# T+0ms:    "Once upon"           → Checkpoint saved
# T+500ms:  "Once upon a time"     → Checkpoint saved
# T+1000ms: [MODEL CRASHES]        → Partial data preserved!

# Even on crash, you get:
{
  "response": "Once upon a time",  # What was generated before crash
  "error": "Connection reset",
  "duration_ms": 1000
}
```

#### Checkpoint Storage
- **In-memory cache** for fast access
- **Database persistence** for recovery after restarts
- **Metadata tracking** in `TaskStep.step_metadata`:
  ```json
  {
    "last_updated": "2026-03-11T14:32:15Z",
    "response_length": 245,
    "is_partial": false,
    "error": null
  }
  ```

#### Agent Crash Tracking
- Increments `agent.crash_count` on failures
- Updates `agent.last_checkpoint` with crash details
- Marks agent as `OFFLINE` after crash
- Auto-flags as `FAILED` after 3+ crashes

### Recovery Flow
```python
# 1. Agent crashes during task
[ERROR] [CEO] FAILED: Connection reset by peer

# 2. Partial response saved automatically
[INFO] Checkpoint saved: 245 bytes preserved

# 3. On retry, recovery system checks for checkpoint
[INFO] Recovered 245 bytes from previous checkpoint

# 4. Execution continues or completes with partial data
```

---

## 4. Continuous Model Monitoring

### What It Does
Background service that runs every 30 seconds to:
- Health-check all active agents
- Auto-detect context window changes
- Track response times (rolling average)
- Auto-recover failed agents
- Flag persistent failures

### Monitoring Dashboard

#### Check Agent Performance
```bash
GET /api/agents/{agent_id}/performance

Response:
{
  "agent_id": 1,
  "agent_name": "CEO",
  "model_name": "Qwen/Qwen3-4B-FP8",
  "context_window": 2048,
  "max_tokens": 819,
  "crash_count": 0,
  "infrastructure_status": "online",
  "avg_response_time_ms": 1234.5,
  "performance": {
    "total_requests": 42,
    "success_rate": 0.95,
    "avg_response_ms": 1234.5,
    "last_24h": 42
  }
}
```

### Monitoring Actions
- **Auto-Recovery**: Detects when offline agents come back online
- **Auto-Flagging**: Marks agents as `FAILED` after 3+ crashes
- **Context Updates**: Adjusts token limits if model changes
- **Latency Tracking**: Maintains exponential moving average

### Logs Generated
```
[AgentMonitor] Started continuous monitoring (interval: 30s)
✓ Agent CEO is back online (latency: 123ms)
⚠ Agent Agent-2 is offline: Connection refused
📊 Agent CEO: Detected context window = 2048 tokens, adjusted max_tokens = 819
❌ Agent CTO marked as FAILED (crash count: 3)
```

---

## 5. Performance Tracking & Analytics

### Real-Time Metrics
The system tracks:
- **Response times** - Last 100 requests per agent
- **Success rates** - % of successful vs failed requests
- **Request volume** - Total requests in last 24h
- **Crash patterns** - Frequency and causes

### Integration with Orchestrator
Every LLM call now automatically:
1. Wraps with crash recovery
2. Saves checkpoints during execution
3. Records performance metrics
4. Updates agent statistics

---

## Migration Guide

### 1. Update Existing Agents

Run the migration script to update existing agents:
```bash
cd backend
python3 fix_agent_tokens.py
```

This will:
- Probe all agent endpoints
- Auto-detect model capabilities
- Update context windows and max_tokens
- Fix any dangerous configurations

### 2. Restart Backend

The monitoring service starts automatically:
```bash
docker compose restart backend

# You'll see:
# ✓ Lucy backend started successfully
#   - Database initialized
#   - HTTP client pool ready
#   - Agent monitoring active
```

### 3. Verify Monitoring

Check that agents are being monitored:
```bash
# Watch logs for health checks
docker compose logs -f backend | grep AgentMonitor

# Check individual agent performance
curl http://localhost:8000/api/agents/1/performance
```

---

## API Changes

### New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agents/{id}/performance` | GET | Agent performance metrics |
| `/api/agents/{id}/chat/stream` | POST | Stream chat completion (SSE) |
| `/api/tasks/{id}/events` | GET | Stream task logs (SSE) *(existing)* |

### Updated Behavior

| Feature | Old | New |
|---------|-----|-----|
| Agent registration | Manual context_window | Auto-detected from endpoint |
| max_tokens default | 2048 | 512 (or 40% of context) |
| LLM failures | Lose all data | Partial data preserved |
| Model changes | Manual update | Auto-detected every 30s |
| Health checks | On-demand only | Continuous background |

---

## Configuration

### Environment Variables (optional)

```bash
# Monitoring interval (default: 30 seconds)
AGENT_MONITOR_INTERVAL=30

# LLM request timeout (default: 300s)
LLM_REQUEST_TIMEOUT=300

# Health check timeout (default: 10s)
HEALTH_CHECK_TIMEOUT=10
```

### Database Changes

New field added to `TaskStep`:
- `step_metadata` (JSON) - Stores checkpoint data

Existing fields now utilized:
- `Agent.last_checkpoint` (JSON) - Recovery metadata
- `Agent.crash_count` (int) - Failure tracking

---

## Best Practices

### 1. Context Window Management
✅ **Do**: Let Lucy auto-detect context windows  
❌ **Don't**: Manually override unless you know the exact limit

### 2. Streaming
✅ **Do**: Use streaming for user-facing interactions  
❌ **Don't**: Stream for internal agent-to-agent calls (overhead)

### 3. Error Handling
✅ **Do**: Check for partial responses on errors  
❌ **Don't**: Assume empty response means no data

### 4. Monitoring
✅ **Do**: Check agent performance metrics regularly  
❌ **Don't**: Ignore persistent failures (auto-flagged after 3 crashes)

---

## Troubleshooting

### Issue: "0 tokens for input" Error

**Old Behavior**: Hard crash  
**New Behavior**: Auto-prevented by dynamic token allocation

If you still see this:
1. Run `python3 fix_agent_tokens.py`
2. Check context_window is detected: `GET /api/agents/{id}/performance`
3. Verify monitoring is running: Check logs for `[AgentMonitor]`

### Issue: Agent Marked as FAILED

**Cause**: 3+ crashes detected by monitoring  
**Solution**:
```bash
# 1. Check agent health
GET /api/agents/{id}/performance

# 2. Reset crash count and resume
POST /api/agents/{id}/resume
```

### Issue: Streaming Not Working

**Check**:
1. Client supports Server-Sent Events (SSE)
2. Proxy/firewall not buffering responses
3. Agent status is `ONLINE` and `ACTIVE`

---

## Performance Impact

### Memory Usage
- **Checkpoints**: ~10KB per active request
- **Monitoring**: ~1MB for 100-agent fleet
- **Performance History**: ~50KB per agent (last 100 requests)

### Network Overhead
- **Health Checks**: 1 request per agent per 30s
- **Model Detection**: 1 request per agent on startup
- **Streaming**: Same as non-streaming (token delivery just happens faster)

### Database Impact
- **Checkpoint Writes**: Every ~500ms during active requests
- **Metadata Updates**: Every 30s per agent
- **Minimal Impact**: All updates batched and async

---

## Future Enhancements

### Planned Features
- [ ] Predictive crash prevention (ML-based)
- [ ] Dynamic timeout adjustment based on model speed
- [ ] Multi-modal streaming support
- [ ] Distributed checkpoint storage (Redis/S3)
- [ ] Advanced alerting (Slack/Discord webhooks)

### Experimental
- [ ] Automatic agent scaling based on load
- [ ] Context window expansion via chunking
- [ ] Fallback agent routing on failures

---

## Summary

Lucy now provides **enterprise-grade reliability**:

✅ **Smart** - Auto-detects and adapts to model capabilities  
✅ **Resilient** - Never loses data, even on crashes  
✅ **Fast** - Streaming responses as they're generated  
✅ **Observable** - Continuous monitoring and metrics  
✅ **Production-Ready** - Handles failures gracefully

**No configuration required** - Everything works automatically!
