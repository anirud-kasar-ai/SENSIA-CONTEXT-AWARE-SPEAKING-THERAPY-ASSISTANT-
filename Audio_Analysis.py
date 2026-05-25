import sensia_bootstrap  # noqa: F401

from langchain_core.prompts import PromptTemplate
import logging
import librosa
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from chat_config import get_chat_llm

logger = logging.getLogger(__name__)

#  Extract relevant features from audio data
def extract_audio_features(audio_data, sample_rate):
    try:
        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)

        # Extract features
        features = {}

        # Volume/amplitude features
        features['rms_energy'] = float(np.sqrt(np.mean(audio_data**2)))

        # Pitch features using librosa
        pitches, magnitudes = librosa.piptrack(y=audio_data, sr=sample_rate)
        features['pitch_mean'] = float(np.mean(pitches[pitches > 0])) if np.any(pitches > 0) else 0.0
        features['pitch_std'] = float(np.std(pitches[pitches > 0])) if np.any(pitches > 0) else 0.0

        # Speech rate approximation
        zero_crossings = librosa.zero_crossings(audio_data)
        features['zero_crossing_rate'] = float(sum(zero_crossings) / len(zero_crossings))

        # Spectral features
        spectral_centroid = librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)[0]
        features['spectral_centroid_mean'] = float(np.mean(spectral_centroid))

        # Spectral contrast for voice expressiveness
        contrast = librosa.feature.spectral_contrast(y=audio_data, sr=sample_rate)
        features['spectral_contrast_mean'] = float(np.mean(contrast))

        # Spectral bandwidth for articulation clarity
        bandwidth = librosa.feature.spectral_bandwidth(y=audio_data, sr=sample_rate)
        features['spectral_bandwidth'] = float(np.mean(bandwidth))

        # Spectral rolloff for brightness or sharpness of sound
        rolloff = librosa.feature.spectral_rolloff(y=audio_data, sr=sample_rate)
        features['spectral_rolloff'] = float(np.mean(rolloff))

        # MFCC features for voice quality
        mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=13)
        features['mfcc_mean'] = [float(x) for x in np.mean(mfccs, axis=1).tolist()]
        features['mfcc_std'] = [float(x) for x in np.std(mfccs, axis=1).tolist()]

        # Rhythm features
        tempo, _ = librosa.beat.beat_track(y=audio_data, sr=sample_rate)
        features['tempo'] = float(tempo)  # Convert to float to avoid numpy array formatting issue

        # by pause detection get silence ratio
        # Define silence threshold
        silence_threshold = 0.01 * features['rms_energy']
        silence_frames = sum(abs(audio_data) < silence_threshold)
        features['silence_ratio'] = float(silence_frames / len(audio_data))

        # Jitter and shimmer (variations in pitch and amplitude)
        # Simplified calculation for demonstration
        hop_length = 512
        frames = librosa.util.frame(audio_data, frame_length=hop_length, hop_length=hop_length)
        frame_energies = np.sqrt(np.sum(frames**2, axis=0))
        features['shimmer'] = float(np.std(frame_energies) / np.mean(frame_energies) if np.mean(frame_energies) > 0 else 0)

        # Energy variance for expressiveness
        features['energy_variance'] = float(np.var(frame_energies))

        # Speaking rate estimation using syllable like energy peaks
        from scipy.signal import find_peaks
        energy_envelope = librosa.feature.rms(y=audio_data)[0]
        peaks, _ = find_peaks(energy_envelope, height=np.mean(energy_envelope))
        duration_in_seconds = len(audio_data) / sample_rate
        features['speaking_rate'] = float(len(peaks) / duration_in_seconds)  # peaks per second

        return features
    except Exception as e:
        logger.warning("Error extracting audio features: %s", e)
        return None

#####################
def display_audio_features(features):
    # Display audio features in a readable format
    # Create two columns of features
    features_1 = {
        'Speech Energy': f"{float(features['rms_energy']):.4f}",
        'Average Pitch (Hz)': f"{float(features['pitch_mean']):.2f}",
        'Pitch Variability': f"{float(features['pitch_std']):.2f}",
        'Speech Rate Indicator': f"{float(features['zero_crossing_rate']):.4f}",
        'Voice Tone Centroid': f"{float(features['spectral_centroid_mean']):.2f}",
        'Speech Tempo (BPM)': f"{float(features['tempo']):.2f}"
    }

    features_2 = {
        'Silence Ratio': f"{float(features['silence_ratio']):.4f}",
        'Vocal Shimmer': f"{float(features['shimmer']):.4f}",
        'Energy Variance': f"{float(features['energy_variance']):.4f}",
        'Speaking Rate (syl/sec)': f"{float(features['speaking_rate']):.2f}",
        'Spectral Contrast': f"{float(features['spectral_contrast_mean']):.2f}",
        'Spectral Bandwidth': f"{float(features['spectral_bandwidth']):.2f}"
    }

    logger.debug("Audio features column 1: %s", features_1)
    logger.debug("Audio features column 2: %s", features_2)

##################################
class AudioReportGenerator:
    def __init__(self, transcription: str, audio_features: dict):
        self.transcription = transcription
        self.audio_features = audio_features

        self.template  = f"""<SYS>
      You are an expert clinical psychologist with extensive experience analyzing speech patterns to assess mental health conditions,
      particularly depression, anxiety, and other mood disorders. Generate a comprehensive clinical report based on the following
      speech data and audio features.

      Transcription: {transcription}

      Audio Features and Their Clinical Significance:
      - Speech energy/volume: {audio_features['rms_energy']:.4f} (Lower values often indicate depression, fatigue, withdrawal)
      - Average pitch: {audio_features['pitch_mean']:.2f} Hz (Depression often shows reduced pitch)
      - Pitch variability: {audio_features['pitch_std']:.2f} (Low variability suggests emotional flattening in depression)
      - Speech rate indicator: {audio_features['zero_crossing_rate']:.4f} (Reduced in psychomotor slowing)
      - Voice tone centroid: {audio_features['spectral_centroid_mean']:.2f} (Lower in depression, higher in anxiety)
      - Speech rhythm/tempo: {audio_features['tempo']:.2f} BPM (Slower in depression, irregular in anxiety)
      - Silence ratio: {audio_features['silence_ratio']:.4f} (Higher values indicate more pauses, common in depression)
      - Vocal shimmer: {audio_features['shimmer']:.4f} (Amplitude irregularity, can indicate emotional distress)
      - Speech energy variance: {audio_features['energy_variance']:.4f} (Lower variance suggests monotone speech)
      - Speaking rate: {audio_features['speaking_rate']:.2f} syllables/sec (Slower rates common in depression)
      - Spectral contrast: {audio_features['spectral_contrast_mean']:.2f} (Lower values suggest reduced expressiveness)
      - Spectral bandwidth: {audio_features['spectral_bandwidth']:.2f} (Related to articulation clarity)

      Based on these measurements and the transcription, create a detailed clinical report with EXACTLY these sections and format:

      ## PSYCHOLOGICAL ASSESSMENT REPORT

      ### 1. Speech Characteristics
      * **Tone and Pitch:** [Analyze pitch variability, monotone qualities, emotional expressiveness]
      * **Speech Rate:** [Assess speed, fluency, pauses, and what they indicate psychologically]
      * **Intensity:** [Evaluate volume, energy levels, and their psychological significance]
      * **Articulation and Prosody:** [Discuss speech clarity, rhythmic features, and their meaning]

      ### 2. Linguistic Features
      * **Word Choice:** [Analyze vocabulary, negative/positive words, self-references]
      * **Sentence Structure:** [Evaluate complexity, organization, coherence]

      ### 3. Nonverbal Cues
      * **Pauses and Hesitations:** [Discuss frequency, duration, and psychological meaning]
      * **Breath Support:** [Analyze breathing patterns evident in the speech]

      ### 4. Emotional and Behavioral Indicators
      * **Emotional Tone:** [Assess overall emotional quality and range]
      * **Engagement Level:** [Evaluate interactive qualities and responsiveness]

      ### 5. Conclusion and Recommendations
      [Provide overall assessment of psychological state, severity of any depression/anxiety indicators, and specific therapeutic recommendations]

      The report should be clinically precise, mentioning specific speech features that indicate depression or other conditions. For each observation, explicitly connect it to the audio measurements. For example: "The patient's pitch variability of 12.3 is significantly below normal range (typically 30-70), strongly indicating emotional flattening consistent with moderate depression."

      This is supportive signal analysis only—not a medical diagnosis. Do not state that the patient has a specific disorder; use cautious language (e.g. "may suggest", "consistent with").

      Make the report detailed and professionally written as if it would be presented to other clinicians. Use clear clinical language throughout.
      </SYS>

      User: {{input_str}} ##
      You:"""
        self._llm = get_chat_llm(temperature=0.3)
        self._prompt = PromptTemplate(input_variables=["input_str"], template=self.template)

    def generate_report(self):
        text = self._prompt.format(input_str="Provide patient report")
        response = self._llm.invoke(text)
        return response.content



##############################
def analyze_with_openai(transcription, features):
    report_gen = AudioReportGenerator(transcription=transcription, audio_features=features)
    report = report_gen.generate_report()
    logger.info("Clinical assessment report generated (%d chars)", len(report or ""))
    return report

