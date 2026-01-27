
# 📺 YouTube Lounge integration

![Version](https://img.shields.io/github/v/release/RoboMagus/home-assistant-youtube-lounge?style=for-the-badge)
![License](https://img.shields.io/github/license/RoboMagus/home-assistant-youtube-lounge.svg?style=for-the-badge)

## ⚠️ Work In Progress

This is very much a Work In Progress custom integration!

Do not use if you aren't ok with things breaking.

## ✨ Features

- Links to YouTube native TV app using _pairing code_.
- Get video info from YouTube API using _API Key_ (Optional).
  - See [references](#references) for instructions on how to create an API Key.
- See what's playing
  - Video Thumbnail
  - Video ID
  - Video Title (Requires API Key)
  - Channel name (Requires API Key)
- Playback controls
  - Play / Pause
  - Volume controls
  - Previous / Next
  - Seek to timestamp
- Play video by `video_id`
  - Play now
  - Add to queue
- Playback state updates instantly using subscription mechanic instead of relying on polling!

**This integration will set up the following platforms.**

| Platform        | Description                                                                    |
| --------------- | ------------------------------------------------------------------------------ |
| `media_player`  | Reflects current playback state of remote YouTube player and enables controls  |
| `binary_sensor` | Diagnostics only (connection, pairing and link states)                         |
| `sensor`        | Currently playing video info (id, title, channel) (Requires API key)           |
| `switch`        | Activate / deactivate subscription required for instant playback state updates |

## References:

- https://pyytlounge.readthedocs.io/
- https://github.com/kieraneglin/pinchflat/wiki/Generating-a-YouTube-API-key
