<h1>Hi! This is my example python 3x-ui wrapper!</h1>
<p>I'm not expecting much to be honest, so please feel free to fork it if I abandon the project and you need it!</p>
<p>Also, if you REALLY want it I can give you the ownership if I step down, you can find my email in the pyproject.toml (I don't check it that much but trust me I do)</p>

<h2>0.0.10 Release Notes</h2>
<ul>
<li>HOTFIX: make models.SingleInboundClient default flow "", because turns out panel can not return it because of zombification...</li>
<li>Add a custom uuid generator for XUIClient that <i>defaults</i> to method in util but you can make your own!</li>
<li>Uncomplicate self.sub_gen into self._resolve_sub</li>
</ul>