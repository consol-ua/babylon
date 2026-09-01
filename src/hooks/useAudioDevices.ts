import { useState, useEffect, useMemo } from 'react';
import { fetchAudioDevices, fetchVoices, fetchSamples, AudioDevice, SampleInfo, GeminiVoice } from '../api';
import { DEFAULT_VOICES } from '../constants';

export interface AudioDeviceState {
  devices: AudioDevice[];
  samples: SampleInfo[];
  voices: GeminiVoice[];
  inputDevices: AudioDevice[];
  outputDevices: AudioDevice[];
  myMicIndex: number | undefined;
  callVirtualMicIndex: number | undefined;
  callInputIndex: number | undefined;
  dubbingInputIndex: number | undefined;
  headphonesIndex: number | undefined;
  setMyMicIndex: (idx: number) => void;
  setCallVirtualMicIndex: (idx: number) => void;
  setCallInputIndex: (idx: number) => void;
  setDubbingInputIndex: (idx: number) => void;
  setHeadphonesIndex: (idx: number) => void;
  isLoopbackRisk: boolean;
}

export function useAudioDevices(): AudioDeviceState {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [voices, setVoices] = useState<GeminiVoice[]>(DEFAULT_VOICES);

  const [myMicIndex, setMyMicIndex] = useState<number | undefined>();
  const [callVirtualMicIndex, setCallVirtualMicIndex] = useState<number | undefined>();
  const [callInputIndex, setCallInputIndex] = useState<number | undefined>();
  const [dubbingInputIndex, setDubbingInputIndex] = useState<number | undefined>();
  const [headphonesIndex, setHeadphonesIndex] = useState<number | undefined>();

  useEffect(() => {
    Promise.all([fetchAudioDevices(), fetchSamples(), fetchVoices()]).then(
      ([devs, smps, vcs]) => {
        setDevices(devs);
        setSamples(smps);
        if (vcs.length > 0) setVoices(vcs);

        const inputs = devs.filter((d) => d.max_input_channels > 0);
        const outputs = devs.filter((d) => d.max_output_channels > 0);

        const defaultMic = inputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || inputs[0];
        const defaultHeadphones = outputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || outputs[0];

        const blackhole2chOut = outputs.find((d) => d.name.toLowerCase().includes("blackhole 2ch"));
        const blackholeGeneralOut = outputs.find((d) => d.name.toLowerCase().includes("blackhole"));
        const selectedVirtualMic = blackhole2chOut || blackholeGeneralOut;

        const blackhole16chIn = inputs.find((d) => d.name.toLowerCase().includes("blackhole 16ch"));
        const blackhole64chIn = inputs.find((d) => d.name.toLowerCase().includes("blackhole 64ch"));
        const otherVirtualIn = inputs.find(
          (d) =>
            d.name.toLowerCase().includes("blackhole") &&
            d.name.toLowerCase() !== selectedVirtualMic?.name.toLowerCase()
        );
        const selectedCallInput = blackhole16chIn || blackhole64chIn || otherVirtualIn;

        if (defaultMic) setMyMicIndex(defaultMic.index);
        if (selectedVirtualMic) setCallVirtualMicIndex(selectedVirtualMic.index);
        if (selectedCallInput) {
          setCallInputIndex(selectedCallInput.index);
        } else {
          const secondaryInput = inputs.find(
            (d) => d.index !== defaultMic?.index && d.name.toLowerCase() !== selectedVirtualMic?.name.toLowerCase()
          );
          if (secondaryInput) setCallInputIndex(secondaryInput.index);
        }

        const dubbingIn =
          inputs.find((d) => d.name.toLowerCase().includes("blackhole 16ch")) ||
          inputs.find((d) => d.name.toLowerCase().includes("blackhole")) ||
          inputs[0];
        if (dubbingIn) setDubbingInputIndex(dubbingIn.index);

        if (defaultHeadphones) setHeadphonesIndex(defaultHeadphones.index);
      }
    );
  }, []);

  const inputDevices = useMemo(() => devices.filter(d => d.max_input_channels > 0), [devices]);
  const outputDevices = useMemo(() => devices.filter(d => d.max_output_channels > 0), [devices]);

  const selectedVirtualMic = useMemo(() => outputDevices.find((d) => d.index === callVirtualMicIndex), [outputDevices, callVirtualMicIndex]);
  const selectedCallInput = useMemo(() => inputDevices.find((d) => d.index === callInputIndex), [inputDevices, callInputIndex]);

  const isLoopbackRisk = useMemo(() => {
    if (!selectedVirtualMic || !selectedCallInput) return false;
    const outName = selectedVirtualMic.name.toLowerCase();
    const inName = selectedCallInput.name.toLowerCase();

    if (outName === inName) return true;
    if (outName.includes("blackhole 2ch") && inName.includes("blackhole 2ch")) return true;
    if (outName.includes("blackhole 16ch") && inName.includes("blackhole 16ch")) return true;
    if (outName.includes("blackhole 64ch") && inName.includes("blackhole 64ch")) return true;
    if (
      outName.includes("blackhole") &&
      inName.includes("blackhole") &&
      !outName.includes("16ch") &&
      !inName.includes("16ch") &&
      !outName.includes("64ch") &&
      !inName.includes("64ch")
    ) {
      return true;
    }
    return false;
  }, [selectedVirtualMic, selectedCallInput]);

  return {
    devices,
    samples,
    voices,
    inputDevices,
    outputDevices,
    myMicIndex,
    callVirtualMicIndex,
    callInputIndex,
    dubbingInputIndex,
    headphonesIndex,
    setMyMicIndex,
    setCallVirtualMicIndex,
    setCallInputIndex,
    setDubbingInputIndex,
    setHeadphonesIndex,
    isLoopbackRisk
  };
}
