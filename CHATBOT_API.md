

## 1. Send a Message

**`POST /main/api/chatbot/send/`**

Start a new conversation or continue an existing one.

### Request Body (JSON)

| Field              | Type   | Required | Description                                                      |
|--------------------|--------|----------|------------------------------------------------------------------|
| `message`          | string | ✅       | The user's message text                                          |
| `conversation_id`  | int    | ❌       | Pass this to continue an existing conversation (enables follow-ups) |
| `session_id`       | string | ❌       | A client-generated UUID to group/retrieve conversations later    |

### Response `200 OK`

```json
{
  "conversation_id": 42,
  "title": "Irene Lunch Registration",
  "message": "Yes – the database shows seven users with \"Irene\" in their name …"
}
```

### Errors

| Status | Body                                          | When                              |
|--------|-----------------------------------------------|-----------------------------------|
| 400    | `{"error": "message is required"}`            | Empty or missing `message`        |
| 403    | `{"error": "session_id does not match ..."}`  | Wrong `session_id` for that convo |
| 404    | `{"error": "Conversation not found"}`         | Invalid `conversation_id`         |
| 500    | `{"error": "<detail>"}`                       | Server / AI provider error        |

### Example: New Conversation

```js
const res = await fetch("/main/api/chatbot/send/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "Do we have Irene in our system?",
    session_id: "550e8400-e29b-41d4-a716-446655440000"   // generate once per device/browser
  })
});
const data = await res.json();
// data.conversation_id → save this for follow-ups
```

### Example: Follow-Up Message

```js
const res = await fetch("/main/api/chatbot/send/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "Give me details about them",
    conversation_id: data.conversation_id,              // from the first response
    session_id: "550e8400-e29b-41d4-a716-446655440000"
  })
});
```

---

## 2. Get Conversation History

**`GET /main/api/chatbot/history/<conversation_id>/`**

Retrieve all messages in a conversation (useful when reloading a previous chat).

### Query Params

| Param        | Type   | Required | Description                                     |
|--------------|--------|----------|-------------------------------------------------|
| `session_id` | string | ❌       | If the conversation was created with one, must match |

### Response `200 OK`

```json
{
  "conversation_id": 42,
  "title": "Irene Lunch Registration",
  "messages": [
    { "role": "user",      "content": "Do we have Irene?",            "created_at": "2026-02-15T14:00:00Z" },
    { "role": "assistant", "content": "Yes – seven users match ...",   "created_at": "2026-02-15T14:00:01Z" },
    { "role": "user",      "content": "Give me details about them",   "created_at": "2026-02-15T14:00:30Z" },
    { "role": "assistant", "content": "Here are the seven Irenes ...", "created_at": "2026-02-15T14:00:31Z" }
  ]
}
```

---

## 3. List Conversations

**`GET /main/api/chatbot/conversations/?session_id=<uuid>`**

List the 20 most recent conversations for a given session.

### Query Params

| Param        | Type   | Required | Description                      |
|--------------|--------|----------|----------------------------------|
| `session_id` | string | ✅       | The client-generated session UUID |

### Response `200 OK`

```json
{
  "conversations": [
    { "id": 42, "title": "Irene Lunch Registration", "created_at": "2026-02-15T14:00:00Z", "updated_at": "2026-02-15T14:01:00Z" },
    { "id": 38, "title": "BBQ Headcount",            "created_at": "2026-02-14T10:00:00Z", "updated_at": "2026-02-14T10:05:00Z" }
  ]
}
```

---

## Typical Frontend Flow

```
1.  Generate a session_id (UUID v4) on first launch → persist in localStorage.

2.  POST /main/api/chatbot/send/
      { message: "...", session_id: "<uuid>" }
    ← { conversation_id: 42, title: "...", message: "..." }

3.  For follow-ups in the same chat, keep sending:
      { message: "...", conversation_id: 42, session_id: "<uuid>" }

4.  To reload a past chat:
      GET /main/api/chatbot/history/42/?session_id=<uuid>

5.  To show a sidebar of past chats:
      GET /main/api/chatbot/conversations/?session_id=<uuid>
```

---

## Notes

- **No authentication required** – conversations are scoped by `session_id`.
- **Follow-up support** – the AI uses conversation history to resolve pronouns like "them", "her", "those people" back to names mentioned earlier.
- **Same data access** – the public chatbot queries the exact same database and uses the same AI pipeline as the admin chatbot.
- Content-Type must be `application/json` for POST requests.
