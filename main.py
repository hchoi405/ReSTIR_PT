from falcor import *

OUT_DIR = "C:/Users/hchoi/repositories/ReSTIR_PT/output"

INTERACTIVE = True

NAME = "BistroExterior2"
FILE = "C:/Users/hchoi/repositories/ORCA/Bistro/BistroExterior.pyscene"
ANIM = [1400, 1500]
METHOD = "input"
REF_COUNT = 65536
SAMPLES_PER_PIXEL = 1
ENABLE_RESTIR = True
MULTIGBUF_COUNT = 4
PATH_SEED_OFFSET = 0

loadRenderPassLibrary("ReSTIRPTPass.dll")
loadRenderPassLibrary("ScreenSpaceReSTIRPass.dll")
loadRenderPassLibrary("GBuffer.dll")
loadRenderPassLibrary("FileloadPass.dll")
loadRenderPassLibrary("OptixDenoiser.dll")
loadRenderPassLibrary("SVGFPass.dll")
loadRenderPassLibrary("CapturePass.dll")
loadRenderPassLibrary("AccumulatePass.dll")

def add_gbuffer(g, init_seed=1):
    dicts = {
        'samplePattern': SamplePattern.Center,
        # sampleCount becomes a seed when used for [Uniform, UniformRandom, CRN] patterns
        # Uniform is for GBufferRaster, UniformRandom is only for GBufferRT (do not use UniformRandom for GBufferRaster)
        'sampleCount': init_seed,
        'useAlphaTest': True,
    }
    GBufferRaster = createPass("GBufferRaster", dicts)  # for input and svgf
    gbuf = "GBufferRaster"
    g.addPass(GBufferRaster, gbuf)
    return gbuf


def add_path(g, gbuf, enable_restir=True, crn=False):

    # Toggle between ReSTIRPT and MegakernelPathTracer
    PathTracer = createPass("ReSTIRPTPass", {
        'samplesPerPixel': SAMPLES_PER_PIXEL,
    })
    path = "ReSTIRPT"
    ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass", {
        'NumReSTIRInstances': SAMPLES_PER_PIXEL,
    })
    screenReSTIR = "ScreenSpaceReSTIR"


    g.addPass(PathTracer, path)
    g.addPass(ScreenSpaceReSTIRPass, screenReSTIR)

    g.addEdge(f"{gbuf}.vbuffer", f"{path}.vbuffer")
    # if enable_restir:
    if True:
        g.addEdge(f"{gbuf}.mvec", f"{path}.motionVectors")
        g.addEdge(f"{gbuf}.vbuffer", f"{screenReSTIR}.vbuffer")
        g.addEdge(f"{gbuf}.mvec", f"{screenReSTIR}.motionVectors")
        g.addEdge(f"{screenReSTIR}.color", f"{path}.directLighting")

    return path, screenReSTIR


def render_input(start, end):
    g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g)
    path, ss_restir = add_path(g, gbuf, enable_restir=ENABLE_RESTIR, crn=False)

    # Connect input/output
    pairs = {
        ## PathTracer
        f'current_{SAMPLES_PER_PIXEL}spp': f"{path}.color",
        # 'temporal': f"{path}.temporalColor",
        # 'envLight': f"{path}.envLight",
        # 'albedo': f"{path}.albedo",

        # ## GBufferRaster
        # 'emissive': f"{gbuf}.emissive",
        # 'normal': f"{gbuf}.normW",
        # 'linearZ': f"{gbuf}.linearZ",
        # 'position': f"{gbuf}.posW",
        # 'mvec': f"{gbuf}.mvec",
        # 'pnFwidth': f"{gbuf}.pnFwidth",
        # 'specRough': f"{gbuf}.specRough",
        # 'diffuseOpacity': f"{gbuf}.diffuseOpacity",
    }
    if ENABLE_RESTIR:
        pairs[f'direct_{SAMPLES_PER_PIXEL}spp'] = f"{ss_restir}.color"
        # pairs['direct2'] = f"{ss_restir}.color2"
        # pairs['directTemporal'] = f"{ss_restir}.temporalColor"
        pass
    opts = {
        'captureCameraMat': True,
        'captureCameraMatOnly': False
    }
    if not INTERACTIVE:
        add_capture(g, pairs, start, end, opts)

    # Add output
    g.markOutput(f"{path}.color")

    return g

graph = render_input(1400, 1500)
FILE = "C:/Users/hchoi/repositories/ORCA/Bistro/BistroExterior.pyscene"
m.addGraph(graph)
m.loadScene(FILE)
m.scene.camera.nearPlane = 0.15 # Increase near plane to prevent Z-fighting

m.clock.framerate = 60
m.clock.time = 0
m.clock.pause()
m.clock.frame = 1400

