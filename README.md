
# 📺 YouTube Lounge integration

![Version](https://img.shields.io/github/v/release/RoboMagus/home-assistant-youtube-lounge?style=for-the-badge)
![License](https://img.shields.io/github/license/RoboMagus/home-assistant-youtube-lounge.svg?style=for-the-badge)

## ⚠️ Work In Progress

This is very much a Work In Progress custom integration!

Do not use if you aren't ok with things breaking.

## ✨ Features

- Links to YouTube native TV app using _pairing code_.
  - See [`Link devices with a TV code`](https://support.google.com/youtube/answer/7640706#zippy=%2Clink-devices-with-a-tv-code) for instructions on finding the TV pairing code.
- Get video info from YouTube API using _API Key_ (Optional).
  - See [this pinchflat wiki](https://github.com/kieraneglin/pinchflat/wiki/Generating-a-YouTube-API-key) for instructions on how to create an API Key.
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
  - Toggle autoplay
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

### Switch

As long as this component is subscribed to the events emitted by the TVs YouTube app, all state updates are immediate. However if the TV is turned off or the YouTube app is inactive we cannot rely on pushed state changes and would instead rely on polling. This would cause both a delay on the state change from inactive to active and might quickly run into API rate limits.

Most TVs expose the current app to HomeAssistant without delay. This component exposes a _switch_ that is intended to be used in an automation to automatically enable the event subscriptions when the YouTube app is activated on the TV. An example automation is shown below:

```yaml
- id: toggle_yt_lounge_tv_on_tv_app
  alias: Toggle YouTube Lounge on TV app
  mode: single
  max_exceeded: silent
  trigger:
    - trigger: state
      entity_id: media_player.lg_tv
      attribute: source
      to:
        - "YouTube"
        - "YouTube AdFree"
    - trigger: state
      entity_id: media_player.lg_tv
      attribute: source
      from:
        - "YouTube"
        - "YouTube AdFree"
      for:
        minutes: 10
  action:
    - variables:
        service: "switch.{{ 'turn_on' if ('YouTube' in state_attr('media_player.lg_tv', 'source')|default(' ',True)) else 'turn_off' }}"
    - action: "{{ service }}"
      target:
        # YouTube Lounge 'switch' entity
        entity_id: switch.youtube_tv_subscribed
```

## References:

- https://pyytlounge.readthedocs.io/
