function convert_dng(dngFile, outTiff)
    if nargin < 2
        outTiff = 'output_uint16.tif';
    end
    t = Tiff(dngFile, 'r');
    cleanup = onCleanup(@() close(t));

    % Helper to safely get a tag (some tags may not exist / throw)
    function v = safeTag(tagname)
        v = [];
        try
            v = getTag(t, tagname);
        catch
        end
    end

    % List subIFD offsets (raw often lives here)
    subOffsets = safeTag('SubIFD');
    if isempty(subOffsets)
        error('No SubIFDs found; this DNG stores everything in page 0 (unsupported compression).');
    end

    fprintf('Main IFD Compression may be unsupported; scanning %d SubIFDs...\n', numel(subOffsets));

    rawFound = false;
    chosenIdx = NaN;

    for i = 1:numel(subOffsets)
        setSubDirectory(t, subOffsets(i));
        comp = safeTag('Compression');            % enum Tiff.Compression.* (if supported)
        phot = safeTag('Photometric');            % enum Tiff.Photometric.*
        sps  = safeTag('SamplesPerPixel');
        bps  = safeTag('BitsPerSample');
        w    = safeTag('ImageWidth');
        h    = safeTag('ImageLength');

        % Basic logging
        try
            compStr = char(comp); % will work for known enums
        catch
            compStr = '<unknown/unsupported>';
        end
        try
            photStr = char(phot);
        catch
            photStr = '<unknown>';
        end
        fprintf('SubIFD %d: %dx%d, SamplesPerPixel=%s, BitsPerSample=%s, Compression=%s, Photometric=%s\n', ...
            i, w, h, mat2str(sps), mat2str(bps), compStr, photStr);

        % Heuristics for picking the raw plane:
        % - Compression is supported (enum available)
        % - 16-bit samples
        % - Prefer Photometric==CFA or SamplesPerPixel==1 (single-plane raw)
        is16 = ~isempty(bps) && all(bps == 16);
        compOK = ~isempty(comp); % if MATLAB recognized it, it's supported
        isLikelyRaw = compOK && is16 && (isequal(phot, Tiff.Photometric.CFA) || isequal(sps, 1) || isequal(sps, [1]));

        if isLikelyRaw
            chosenIdx = i;
            rawFound = true;
            break
        end
    end

    if ~rawFound
        % Fallback: pick the first SubIFD that MATLAB can read() at all
        for i = 1:numel(subOffsets)
            try
                setSubDirectory(t, subOffsets(i));
                test = read(t); %#ok<NASGU>
                chosenIdx = i;
                rawFound = true;
                warning('No obvious CFA plane; falling back to first readable SubIFD %d.', i);
                break
            catch
            end
        end
    end

    if ~rawFound
        error(['Could not find a readable SubIFD. This DNG likely uses a private compression in all IFDs. ' ...
               'Use dcraw_emu as in Option B.']);
    end

    % Read chosen SubIFD losslessly
    setSubDirectory(t, subOffsets(chosenIdx));
    raw = read(t);          % returns uint16 if file stores 16-bit
    if ~isa(raw, 'uint16')
        error('Unexpected dtype (%s). Stopping to avoid silent conversion.', class(raw));
    end

    % Save as uncompressed 16-bit TIFF (no scaling, no demosaic)
    imwrite(raw, outTiff, 'tif', 'Compression', 'none');
    fprintf('Saved uncompressed 16-bit TIFF: %s\n', outTiff);
end
