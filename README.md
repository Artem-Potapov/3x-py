<h1>Hi! This is my example python 3x-ui wrapper!</h1>
<p>I'm not expecting much to be honest, so please feel free to fork it if I abandon the project and you need it!</p>
<p>Also, if you REALLY want it I can give you the ownership if I step down, you can find my email in the pyproject.toml (I don't check it that much but trust me I do)</p>

<h2>0.0.9 Release Notes</h2>
<ul>
<li>Fix _request_update_client for it to actually work and NOT create "zombies"</li>
<li>DTO un-split because fields reset when not provided, so full inbounds must be fetched</li>
<li>New method: update_client_by_tgid</li>
<li>Fixed test suite</li>
<li>Fix from_response and from_list</li>
<li>Remove obsolete and useless client fields from models</li>
<li>Inbound settings actually get parsed properly into ClientsSettings</li>
<li>New asyncio task management so they won't get destroyed when GCed</li>
<li>XUIClient async_lru cache now binds to event loop at runtime, not in initialization</li>
</ul>