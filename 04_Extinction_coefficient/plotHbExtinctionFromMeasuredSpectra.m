function plotHbExtinctionFromMeasuredSpectra()
    % Load extinction coefficients (Prahl data)
    % Format: [wavelength, HbO2, Hb]
    prahl = load('prahl_extinction.txt');  % Ensure this file exists in path
    wl = prahl(:,1);         % Wavelengths in nm
    epsHbO2 = prahl(:,2);    % cm^-1/M
    epsHb   = prahl(:,3);    % cm^-1/M

    % Load measured spectra from Excel
    spectra = readtable('led_525nm.xlsx', 'VariableNamingRule', 'preserve');

    % Extract wavelengths and channel names
    rawWavelengths = spectra{:,1};
    rawData = spectra{:,2};
    channels = spectra.Properties.VariableNames(2);

    % Average repeated rows by wavelength
    [wavelengths, ~, idxGroup] = unique(rawWavelengths);
    averagedSpectra = zeros(length(wavelengths), size(rawData,2));
    for i = 1:length(wavelengths)
        averagedSpectra(i,:) = mean(rawData(idxGroup==i,:), 1, 'omitnan');
    end

    % Interpolate extinction coefficients
    epsHbO2_interp = interp1(wl, epsHbO2, wavelengths, 'linear', NaN);
    epsHb_interp   = interp1(wl, epsHb, wavelengths, 'linear', NaN);

    % Remove wavelengths outside Prahl data range
    validIdx = ~isnan(epsHbO2_interp) & ~isnan(epsHb_interp);
    wavelengths = wavelengths(validIdx);
    averagedSpectra = averagedSpectra(validIdx, :);
    epsHbO2_interp = epsHbO2_interp(validIdx);
    epsHb_interp   = epsHb_interp(validIdx);

    % Normalize spectra so area under each curve = 1
    % normSpectra = averagedSpectra ./ sum(averagedSpectra, 1, 'omitnan');
    area = trapz(wavelengths, averagedSpectra, 1);
    if ~(isfinite(area) && area > 0)
        error('Area under the curve is not finite or positive. Check your data.');
    end
    normSpectra = averagedSpectra ./ area;

    % Compute effective extinction coefficients
    % epsHbO2_eff = normSpectra' * epsHbO2_interp;
    % epsHb_eff   = normSpectra' * epsHb_interp;
    epsHbO2_eff = trapz(wavelengths, normSpectra .* epsHbO2_interp);
    epsHb_eff   = trapz(wavelengths, normSpectra .* epsHb_interp);

    % Plot 1: Normalized Spectra
    figure;
    plot(wavelengths, normSpectra, 'LineWidth', 1.5);
    xlabel('Wavelength (nm)');
    ylabel('Normalized Intensity');
    title('Normalized Illumination Spectra per Channel');
    legend(channels, 'Location', 'best');
    grid on;

    % Plot 2: Effective Extinction Coefficients
    figure;
    bar(categorical(channels), [epsHbO2_eff, epsHb_eff]);
    ylabel('Effective Extinction Coefficient (cm^{-1}/M)');
    legend('HbO2', 'Hb');
    title('Effective ε per Channel');
    grid on;

    % Print table
    % disp(scatter(channels', epsHbO2_eff, epsHb_eff, ...
    %    'VariableNames', {'Channel','HbO2_cm1M','Hb_cm1M'}));
    T = table(string(channels), epsHbO2_eff, epsHb_eff, ...
        'VariableNames', {'Channel', 'HbO2_cm1M', 'Hb_cm1M'});
    disp(T);

    categorical(channels)

    [epsHbO2_eff, epsHb_eff]

end
