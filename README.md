<h1>Hi! This is my example python 3x-ui wrapper!</h1>
<p>I'm not expecting much to be honest, so please feel free to fork it if I abandon the project and you need it!</p>
<p>Also, if you REALLY want it I can give you the ownership if I step down, you can find my email in the pyproject.toml (I don't check it that much but trust me I do)</p>

<h2>0.0.9-r3 Release Notes</h2>
<ul>
<li>HOTFIX: the importing of util.py fixed with from __future__ import annotations</li>
<li>Make panel_id for better accounting & logging clarity</li>
<li>Fix __aenter__ in XUIClient to not log a warning</li>
<li>Fix total_gb to be int and not float, since that would need refactoring which I don't have time for yet.</li>
<li>ClientsSettings now has extra=ignore instead of extra=forbid.</li>
</ul>