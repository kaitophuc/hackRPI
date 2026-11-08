"""Compile an isolated direct-vertex prototype without editing production sources."""
import pathlib,shutil,subprocess

root=pathlib.Path(__file__).resolve().parents[3];folder=root/'build/software-profile/vertex-candidate'
folder.mkdir(exist_ok=True)
for source in (root/'combat/src').glob('*.cs'):
    if source.name!='Desktop.cs':shutil.copyfile(source,folder/source.name)
shutil.copyfile(pathlib.Path(__file__).with_name('VertexBuffer.cs'),folder/'VertexBuffer.cs')
def replace(name,old,new):
    path=folder/name;text=path.read_text()
    if text.count(old)!=1:raise RuntimeError('Unexpected prototype marker in '+name)
    path.write_text(text.replace(old,new))
replace('Math3D.cs','public List<Vertex> Vertices=new List<Vertex>();','public VertexBuffer Vertices=new VertexBuffer();')
replace('SpinalVoodooRenderer.cs','readonly bool reusePacking=',
        'readonly bool directVertices=Environment.GetEnvironmentVariable("FLIGHTING_DIRECT_VERTEX_BUFFER")=="1";\n    readonly bool reusePacking=')
replace('SpinalPipeline.cs','''PackedDraw packed=Packing(drawSlot++,d.Vertices.Count,d.Indices.Count);
                d.Vertices.CopyTo(packed.Vertices);d.Indices.CopyTo(packed.Indices);''',
        '''PackedDraw packed=Packing(drawSlot++,directVertices?0:d.Vertices.Count,d.Indices.Count);
                IntPtr vertexAddress;
                if(directVertices)vertexAddress=d.Vertices.PinData();
                else{d.Vertices.CopyTo(packed.Vertices);vertexAddress=packed.VertexAddress;}
                d.Indices.CopyTo(packed.Indices);''')
replace('SpinalPipeline.cs','fg_prepared_add_vertices(target.Handle,packed.VertexAddress,','fg_prepared_add_vertices(target.Handle,vertexAddress,')
replace('SpinalPipeline.cs','target.NativePrepareMs+=watch.Elapsed.TotalMilliseconds-prepareStarted;',
        'target.NativePrepareMs+=watch.Elapsed.TotalMilliseconds-prepareStarted;\n                if(directVertices)GC.KeepAlive(d.Vertices);')
csc=r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
sources=[str(p) for p in folder.glob('*.cs')]
base=[csc,'/nologo','/target:exe','/platform:anycpu','/optimize+','/r:System.dll','/r:System.Core.dll','/r:System.Runtime.Serialization.dll']
targets=[('VertexCandidate.exe','Flighting.Program',None),
         ('VertexProfile.exe','ProfileSoftware',root/'combat/experiments/software_profile/ProfileSoftware.cs'),
         ('VertexPixels.exe','PipelineValidation',root/'combat/tests/PipelineValidation.cs'),
         ('VertexDepthModes.exe','DepthModeValidation',root/'combat/experiments/software_profile/DepthModeValidation.cs'),
         ('VertexBufferChecks.exe','VertexBufferChecks',root/'combat/experiments/software_profile/VertexBufferChecks.cs')]
for output,main,extra in targets:
    command=base+['/define:CURRENT','/main:'+main,'/out:'+str(folder/output)]+sources
    if extra:command.append(str(extra))
    subprocess.run(command,check=True)
baseline=[str(p) for p in (root/'combat/src').glob('*.cs') if p.name!='Desktop.cs']
subprocess.run(base+['/define:CURRENT','/main:ProfileSoftware','/out:'+str(root/'build/software-profile/BeforeVertexProfile.exe')]+baseline+
               [str(root/'combat/experiments/software_profile/ProfileSoftware.cs')],check=True)
print('Built isolated vertex-storage candidates in',folder)
