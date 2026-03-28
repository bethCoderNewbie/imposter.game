---                                                                                                      
  Technical Design: Landing Page & Lobby/Join Flow                                                                                                                                                                    
  ---                                                                                                        Architecture Overview                                                                                                                                                                                                 Two clients participate: Display (browser/TV, hosts the match) and Mobile (per-player controller). A       third actor is the Backend (FastAPI + WebSocket). The lobby flow is the handshake between all three        before game start.                                                                                                                                                                                                    ---                                                                                                        1. Landing Page (Display Client)                                                                                                                                                                                      File: frontend-display/src/App.tsx — CreateMatchScene component (lines 85–287)                           

  Scene Trigger

  Rendered when App.tsx has no match_id in URL params. Transitions to LobbyScene after match creation.

  Responsibilities

  - Allow the display host to create a new match
  - Allow the display host to resume a previously saved match by entering a match_id

  API Calls

  ┌──────────────┬────────┬──────────┬────────────────────┬──────────────────────────┐
  │    Action    │ Method │ Endpoint │    Request Body    │         Response         │
  ├──────────────┼────────┼──────────┼────────────────────┼──────────────────────────┤
  │ Create match │ POST   │ /matches │ { num_players: 4 } │ { match_id, host_token } │
  └──────────────┴────────┴──────────┴────────────────────┴──────────────────────────┘

  - On success: URL is updated to ?match_id={id}&host_token={token} and App.tsx transitions scene to
  'lobby'
  - host_token is persisted only in URL params — never in localStorage

  Local State

  ┌─────────────┬─────────┬────────────────────────────────────────┐
  │    State    │  Type   │                Purpose                 │
  ├─────────────┼─────────┼────────────────────────────────────────┤
  │ loading     │ boolean │ Disable button during POST             │
  ├─────────────┼─────────┼────────────────────────────────────────┤
  │ showResume  │ boolean │ Toggle collapse for resume input panel │
  ├─────────────┼─────────┼────────────────────────────────────────┤
  │ resumeId    │ string  │ Text input value for saved match ID    │
  ├─────────────┼─────────┼────────────────────────────────────────┤
  │ resumeError │ string  │ Error display for resume path          │
  └─────────────┴─────────┴────────────────────────────────────────┘

  ---
  2. Lobby Scene (Display Client)

  File: frontend-display/src/scenes/LobbyScene.tsx

  Scene Trigger

  Rendered by App.tsx when scene === 'lobby'. Transitions to 'board' scene on game start.

  Props

  {
    matchId: string,
    mobileBaseUrl: string,      // base URL for QR code target
    onNewMatch: () => void,
    onStartGame?: () => void    // only defined when host_token is present in URL
  }

  Responsibilities

  - Display QR code pointing to {mobileBaseUrl}?match_id={matchId}
  - Show live player roster (populated via WebSocket match_data events)
  - Allow the display host to start the game (requires ≥1 player joined)
  - Show "New Match" button to reset

  Roster Data Source

  - Read from Zustand store: roster: PlayerRosterEntry[]
  - Updated exclusively by incoming match_data WebSocket messages
  - MAX_PLAYERS = 4; empty slot rows rendered for unfilled positions

  API Calls

  ┌──────────┬────────┬───────────────────────────┬─────────────────┬──────────────┬─────────────────┐     
  │  Action  │ Method │         Endpoint          │      Auth       │ Request Body │    Response     │     
  ├──────────┼────────┼───────────────────────────┼─────────────────┼──────────────┼─────────────────┤     
  │ Start    │ POST   │ /matches/{match_id}/start │ host_token in   │ { host_token │ { match_id,     │     
  │ game     │        │                           │ body            │  }           │ seed }          │     
  └──────────┴────────┴───────────────────────────┴─────────────────┴──────────────┴─────────────────┘     

  - On success: backend broadcasts full sync to all WebSocket clients; App transitions to 'board'
  - Start button is disabled when roster.length === 0

  WebSocket Connection

  - Display connects to /ws/{match_id} as spectator: { player_id: null, credentials: null }
  - Listens for sync, update, match_data messages
  - Does not send moves; receives all broadcasts

  ---
  3. Join Page (Mobile Client)

  File: frontend-mobile/src/pages/JoinPage.tsx

  View Trigger

  Rendered by App.tsx when appState === 'join'. Transitions to 'waiting' (or 'game' if match already       
  started).

  Responsibilities

  - Accept a match_id (pre-filled from ?match_id= URL param if scanned via QR)
  - Accept a player name
  - Join the match and receive credentials
  - Offer a "Rejoin" flow for returning to a started match (collapsed by default, auto-shown on 409        
  already-started)
  - Display stored credentials from localStorage to allow resuming without re-entering info

  Local State

  ┌──────────────────────────────────┬────────────────────────────┬────────────────────────────────────┐   
  │              State               │            Type            │              Purpose               │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ matchId                          │ string                     │ Controlled input for match ID      │
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ playerName                       │ string                     │ Controlled input for name          │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ error                            │ string                     │ Join error display                 │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ loading                          │ boolean                    │ Disable button during POST         │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ matchInfo                        │ { players_joined,          │ Live player count (polled once on  │   
  │                                  │ num_players } | null       │ mount if URL has match_id)         │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ storedForResume                  │ StoredCredentials | null   │ Loaded from localStorage on mount  │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ showRejoin                       │ boolean                    │ Toggle rejoin panel                │   
  ├──────────────────────────────────┼────────────────────────────┼────────────────────────────────────┤   
  │ rejoinMatchId/Name/Error/Loading │ various                    │ Rejoin panel state                 │   
  └──────────────────────────────────┴────────────────────────────┴────────────────────────────────────┘   

  localStorage Key

  brass_credentials — stores StoredCredentials:
  {
    match_id: string,
    player_id: string,
    credentials: string,
    player_name: string
  }

  API Calls

  ┌────────┬────────┬────────────────────────────┬─────────────┬───────────────────┬─────────────────┐     
  │ Action │ Method │          Endpoint          │  Request    │     Response      │      Notes      │     
  │        │        │                            │    Body     │                   │                 │     
  ├────────┼────────┼────────────────────────────┼─────────────┼───────────────────┼─────────────────┤     
  │ Fetch  │        │                            │             │ { players_joined, │ Called on mount │     
  │ count  │ GET    │ /matches/{match_id}        │ —           │  num_players }    │  if URL has     │     
  │        │        │                            │             │                   │ match_id        │     
  ├────────┼────────┼────────────────────────────┼─────────────┼───────────────────┼─────────────────┤     
  │        │        │                            │ {           │ { player_id,      │ 409 if full or  │     
  │ Join   │ POST   │ /matches/{match_id}/join   │ player_name │ credentials }     │ started         │     
  │        │        │                            │  }          │                   │                 │     
  ├────────┼────────┼────────────────────────────┼─────────────┼───────────────────┼─────────────────┤     
  │        │        │                            │ {           │ { player_id,      │ Invalidates old │     
  │ Rejoin │ POST   │ /matches/{match_id}/rejoin │ player_name │ credentials }     │  token          │     
  │        │        │                            │  }          │                   │                 │     
  └────────┴────────┴────────────────────────────┴─────────────┴───────────────────┴─────────────────┘     

  - Join success: credentials saved to localStorage → onJoin(creds) callback fires → App transitions to    
  'waiting'
  - Rejoin success: same callback, App may transition directly to 'game' if match already started

  ---
  4. Waiting Room (Mobile Client)

  File: frontend-mobile/src/pages/WaitingRoom.tsx

  View Trigger

  Rendered by App.tsx when appState === 'waiting'. Transitions to 'game' on game start broadcast.

  Props

  {
    match_id: string,
    player_id: string,
    credentials: string,
    onLeave: () => void
  }

  Responsibilities

  - Show live roster (name, color dot, ready/waiting status) via WebSocket match_data
  - Show WebSocket connection status
  - Host-only: Start Game button (requires all roster entries connected)
  - Host-only: Save Game button (extends server TTL to 7 days)
  - Allow any player to leave (clears localStorage)

  Host Detection

  isHost = roster[0]?.id === player_id
  First player to join (p1) is always host.

  Local State

  ┌─────────────────────────────────────┬─────────────────────┬─────────────────────────────────────────┐  
  │                State                │        Type         │                 Purpose                 │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ roster                              │ PlayerRosterEntry[] │ From Zustand store                      │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ connectionStatus                    │ string              │ From Zustand store                      │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ isHost                              │ boolean             │ Computed from roster[0]                 │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ matchAlreadyStarted                 │ boolean             │ Fetched on mount; disables start button │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ starting / startError               │ boolean / string    │ Start button state                      │  
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────────────────────────┤  
  │ saving / saveError / savedConfirmed │ various             │ Save button state                       │  
  └─────────────────────────────────────┴─────────────────────┴─────────────────────────────────────────┘  

  API Calls

  ┌──────────┬────────┬───────────────────────────┬─────────────┬──────────────┬───────────────────────┐   
  │  Action  │ Method │         Endpoint          │    Auth     │ Request Body │       Response        │   
  ├──────────┼────────┼───────────────────────────┼─────────────┼──────────────┼───────────────────────┤   
  │ Check    │ GET    │ /matches/{match_id}       │ —           │ —            │ { started }           │   
  │ started  │        │                           │             │              │                       │   
  ├──────────┼────────┼───────────────────────────┼─────────────┼──────────────┼───────────────────────┤   
  │ Start    │        │                           │             │ {            │                       │   
  │ game     │ POST   │ /matches/{match_id}/start │ credentials │ credentials  │ { match_id, seed }    │   
  │          │        │                           │             │ }            │                       │   
  ├──────────┼────────┼───────────────────────────┼─────────────┼──────────────┼───────────────────────┤   
  │ Save     │        │                           │             │ {            │ { saved,              │   
  │ match    │ POST   │ /matches/{match_id}/save  │ credentials │ credentials  │ expires_in_seconds }  │   
  │          │        │                           │             │ }            │                       │   
  └──────────┴────────┴───────────────────────────┴─────────────┴──────────────┴───────────────────────┘   

  - Start triggers backend to broadcast full sync → all clients transition to game view
  - Save sets meta.saved_by_host = true; extends Redis TTL to 604800s (7 days)

  WebSocket Connection

  - Mobile connects to /ws/{match_id} with { player_id, credentials }
  - WS hook (useGameState) sends handshake sync message on open
  - Roster populated by incoming match_data events

  ---
  5. Backend Endpoints (Summary)

  Router prefix: /matches — backend-engine/api/lobby/router.py

  ┌─────┬────────┬────────────────────────────┬────────────────────┬───────────────────────────────────┐   
  │  #  │ Method │            Path            │        Auth        │              Purpose              │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 1   │ POST   │ /matches                   │ None               │ Create match; returns match_id +  │   
  │     │        │                            │                    │ host_token                        │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 2   │ GET    │ /matches                   │ None               │ List public matches               │   
  │     │        │                            │                    │ (unlisted=false only)             │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 3   │ GET    │ /matches/{match_id}        │ None               │ Read roster, started flag, era    │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 4   │ POST   │ /matches/{match_id}/join   │ None               │ Register player; returns          │   
  │     │        │                            │                    │ player_id + credentials           │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 5   │ POST   │ /matches/{match_id}/rejoin │ None (name-match   │ Re-issue credentials; invalidates │   
  │     │        │                            │ check)             │  old token                        │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 6   │ POST   │ /matches/{match_id}/start  │ credentials or     │ Initialize full game state;       │   
  │     │        │                            │ host_token         │ broadcast sync                    │   
  ├─────┼────────┼────────────────────────────┼────────────────────┼───────────────────────────────────┤   
  │ 7   │ POST   │ /matches/{match_id}/save   │ credentials (host  │ Extend Redis TTL to 7 days        │   
  │     │        │                            │ only)              │                                   │   
  └─────┴────────┴────────────────────────────┴────────────────────┴───────────────────────────────────┘   

  Player ID assignment: sequential strings p1, p2, p3, p4 in join order.
  Credentials: secrets.token_urlsafe(32) opaque tokens; stored in
  _match_metadata[match_id]["credentials"][player_id]; overwritten on rejoin.
  Redis TTL: Default 86400s (24h); host save extends to 604800s (7d).

  ---
  6. WebSocket Handshake (Lobby Phase)

  Endpoint: ws://{host}/ws/{match_id} — backend-engine/api/ws/endpoint.py

  Connection Sequence

  1. Client opens WS connection
  2. Client sends first message (MUST be sync type):
  { type: "sync", match_id, player_id: string | null, credentials: string | null }
  2. Spectator (Display): player_id=null, credentials=null
  3. Server validates credentials; sends ErrorMessage { error: "UNAUTHORIZED" } and closes on failure      
  4. Server registers socket; marks player is_connected = true in metadata
  5. Server sends full SyncMessage to new client
  6. Server broadcasts MatchDataMessage (updated roster) to ALL sockets in match

  MatchDataMessage (roster broadcast)

  {
    type: "match_data",
    players: [{ id, name, is_connected }],
    player_status: { /* idle | consulting_rulebook */ }
  }
  This is the primary mechanism by which the Lobby Scene and Waiting Room populate their player rosters.   

  ---
  7. State Store (Shared — Lobby-Relevant Fields)

  File: packages/shared/src/useGameStore.ts (Zustand)

  ┌──────────────────┬──────────────────────────────────────┬────────────────────┬─────────────────────┐   
  │      Field       │                 Type                 │       Set By       │       Used By       │   
  ├──────────────────┼──────────────────────────────────────┼────────────────────┼─────────────────────┤   
  │ roster           │ PlayerRosterEntry[]                  │ setRoster() on     │ LobbyScene,         │   
  │                  │                                      │ match_data         │ WaitingRoom         │   
  ├──────────────────┼──────────────────────────────────────┼────────────────────┼─────────────────────┤   
  │ connectionStatus │ 'connecting' | 'connected' |         │ WS lifecycle       │ WaitingRoom status  │   
  │                  │ 'disconnected' | 'error'             │                    │ indicator           │   
  ├──────────────────┼──────────────────────────────────────┼────────────────────┼─────────────────────┤   
  │ G, ctx, state_id │ game state                           │ sync() / update()  │ Post-lobby game     │   
  │                  │                                      │                    │ views               │   
  └──────────────────┴──────────────────────────────────────┴────────────────────┴─────────────────────┘   

  ---
  8. Data Flow (Lobby Phase End-to-End)

  Display                Backend                  Mobile(s)
     |                      |                         |
     |-- POST /matches ----> |                         |
     |<-- {match_id,         |                         |
     |     host_token} ------|                         |
     |                       |                         |
     |-- WS /ws/{match_id} ->|                         |
     |   {player_id: null}   |                         |
     |<-- sync (empty G) ----|                         |
     |                       |                         |
     |  [QR scanned by       |                         |
     |   mobile player]      |                         |
     |                       |<-- POST /join ----------|
     |                       |--- {player_id, creds} ->|
     |                       |                         |
     |                       |<-- WS /ws/{match_id} ---|
     |                       |    {player_id, creds}   |
     |<-- match_data --------|-- match_data ----------->|
     |   (roster updated)    |   (roster updated)      |
     |                       |                         |
     |-- POST /start ------> |  (display is host)      |
     |                       |-- sync (full G) -------->|
     |<-- sync (full G) -----|                         |
     |  [transitions to      |                [transitions to
     |   BoardScene]         |                 game view]

  ---
  Key Design Constraints

  - host_token (display host auth) and credentials (player auth) are both accepted by /start — either can  
  launch the game
  - Rejoin immediately invalidates the prior token; there is no grace period
  - The WebSocket match_data broadcast is the sole source of truth for roster state in all lobby UI        
  components — no polling
  - state_id fencing (ADR-004) is enforced on every move but is irrelevant during the pre-start lobby phase