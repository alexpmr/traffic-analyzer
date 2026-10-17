"""Execute actual role SVG/Leaflet logic and preserve MeshMonitor metadata."""
import json
from pathlib import Path
import subprocess
import unittest
import traffic_analyzer as ta
import traffic_analyzer_web as web

class RoleIconTests(unittest.TestCase):
    def test_real_svg_roles_and_activity_colors(self):
        html=web.HTML
        icons=html[html.index('const NODE_ROLE_META='):html.index('function roleFriendly(')]
        activity=html[html.index('function normalizeObservedTimestampMs('):html.index('function cutoffForSelection(')]
        js="const nodeTrafficLastSeen=new Map();const tr=x=>x;const L={divIcon:x=>x};\n"+activity+icons+'''
const now=Date.now();
const rows=NODE_ROLE_META.map((row,i)=>({role:nodeRoleMeta(i)[0],svg:nodeRoleSvg(i,'#2ecc71')}));
const color=n=>nodeRoleIcon(n).html;
console.log(JSON.stringify({rows,
 zero:nodeRoleMeta(0)[0],base:nodeRoleMeta('12')[0],router:nodeRoleMeta('router')[0],
 missing:[null,undefined,'',true,999,'<svg onload=bad>'].map(x=>nodeRoleMeta(x)[0]),
 colors:[now-1000,now-3*3600000,now-3*86400000,0].map(lastHeard=>color({nodeNum:1,role:2,lastHeard})),
 stale:color({nodeNum:2,role:12,lastHeard:now-3*86400000,lastSeenMs:now}),
 icon:nodeRoleIcon({role:0}),legend:nodeRoleLegendHtml()}));
'''
        result=json.loads(subprocess.check_output(['node','-e',js],text=True))
        self.assertEqual(len({r['svg'] for r in result['rows']}),13)
        self.assertEqual(result['zero'],'CLIENT');self.assertEqual(result['base'],'CLIENT_BASE')
        self.assertEqual(result['router'],'ROUTER')
        self.assertEqual(set(result['missing']),{'UNKNOWN'})
        for svg,color in zip(result['colors'],['#2ecc71','#f39c12','#e74c3c','#7f8c8d']):self.assertIn(color,svg)
        self.assertIn('#e74c3c',result['stale'])
        self.assertEqual(result['icon']['iconAnchor'],[17,17])
        self.assertIn('<details',result['legend'])
        self.assertEqual(result['legend'].count('roleLegendItem'),14)

    def test_topology_and_history_keep_role_zero_and_missing_updates(self):
        for role in [0,2,12,'ROUTER_LATE']:
            nodes={12345:{'nodeNum':12345,'longName':'Known','role':role,'latitude':-15.8,'longitude':-47.8}}
            topology=ta.build_topology(nodes,[],1700000000000)
            self.assertEqual(topology['nodes'][0]['role'],role)
            merged,_=web._history_merge_node_json(topology['nodes'][0],{'role':None},1700000001000)
            self.assertEqual(merged['role'],role)
        merged,_=web._history_merge_node_json({'role':2},{'role':0},1700000001000)
        self.assertEqual(merged['role'],0)
