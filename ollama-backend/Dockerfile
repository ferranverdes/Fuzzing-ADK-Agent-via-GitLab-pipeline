FROM ollama/ollama:0.16.2

# Bind Ollama to all network interfaces on port 8080
ENV OLLAMA_HOST 0.0.0.0:8080

# Directory where Ollama stores downloaded model files
ENV OLLAMA_MODELS /models

# Disable debug logging to reduce console noise
ENV OLLAMA_DEBUG false

# Prevent Ollama from unloading models from memory.
# By default, Ollama may release model weights after inactivity to
# free GPU memory. When this happens, the GPU becomes idle and the
# next request triggers a cold start: weights must be read from disk
# and transferred back into VRAM, which can introduce noticeable
# latency. Keeping models resident avoids GPU reinitialization and
# ensures consistently low response times.
ENV OLLAMA_KEEP_ALIVE -1

# Preload the model during the image build so weights are baked
# into the container image. This removes runtime downloads and
# eliminates model-fetch delays at container startup.
ENV MODEL mistral:7b
RUN ollama serve & sleep 5 && ollama pull $MODEL

# Launch Ollama when the container starts
ENTRYPOINT ["ollama", "serve"]
