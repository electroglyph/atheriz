from importlib import metadata
from atheriz.singletons.objects import filter_by
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

SCREEN = r"""
   _____   __  .__                 .____________
  /  _  \_/  |_|  |__   ___________|__\____    /
 /  /_\  \   __\  |  \_/ __ \_  __ \  | /     / 
/    |    \  | |   Y  \  ___/|  | \/  |/     /_ 
\____|__  /__| |___|  /\___  >__|  |__/_______ \
        \/          \/     \/                 \/                                  
                                                                        
                                                                  
         ATHERIZ VERSION = {version}
       KNOWN ADVENTURERS = {known}
      ONLINE ADVENTURERS = {online}

enter 'sr' for screenreader mode
enter 'connect <account> <password>' to login
"""

SCREEN2 = r"""
                  
         ATHERIZ VERSION = {version}
       KNOWN ADVENTURERS = {known}
      ONLINE ADVENTURERS = {online}

enter 'sr' for screenreader mode
enter 'connect <account> <password>' to login
"""


def get_online():
    results: list[Object] = filter_by(lambda x: x.is_pc)
    return (sum(1 for x in results if x.is_connected), len(results))


def render(session=None):
    online = get_online()
    if session and session.screenreader:
        return SCREEN2.format(
            version=metadata.version("atheriz"), known=f"{online[1]}", online=f"{online[0]}"
        )
    return SCREEN.format(
        version=metadata.version("atheriz"), known=f"{online[1]}", online=f"{online[0]}"
    )
