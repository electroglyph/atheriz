# 11 Recipes & Tutorials

## 11.1 Recipe: Custom Client Messages

This recipe demonstrates how to receive and process custom JSON payloads sent from a specialized client (like a web-based UI or map renderer).

### 11.1.1 Target Goal
We want to support a custom web client that sends a `"minimap_click"` payload when the user clicks a coordinate on an external map UI. 

The expected JSON message from the client is:
```json
["minimap_click", [5, 2], {}]
```

### 11.1.2 Implementation

1. Create a custom `InputFuncs` class in your game folder (`my_game/inputfuncs.py`).
2. Import the `@inputfunc` decorator and apply it to a new method. The string passed to the decorator must match the message name.

```python
# In my_game/inputfuncs.py
from atheriz.inputfuncs import InputFuncs, inputfunc
from atheriz.pathfind import calculate_path

class CustomInputFuncs(InputFuncs):
    
    @inputfunc("minimap_click")
    def handle_map_click(self, connection, *args, **kwargs):
        # Extract the character attached to this connection
        session = connection.session
        if not session or not session.puppet:
            return
            
        character = session.puppet
        
        # Extract the payload arguments
        target_x, target_y = args[0]
        target_area = character.location.coord[0]
        target_z = character.location.coord[3]
        
        target_coord = (target_area, target_x, target_y, target_z)
        
        # Output feedback safely to the player
        character.msg(f"Setting course to {target_coord}...")
        
        # (Optional) Implement pathfinding step logic here using calculate_path
```

3. Ensure the custom class is injected within your `settings.py`:
```python
# In my_game/settings.py
CLASS_INJECTIONS = [
    ("inputfuncs", "CustomInputFuncs", "atheriz.inputfuncs"),
    # ... other injections
]
```

When the client transmits the JSON array, the Atheriz WebSocket layer decodes it safely and dispatches the data accurately to the `handle_map_click` method block.

[Table of Contents](./table_of_contents.md) | [Next: 12 API Reference](./12_api_reference.md)
