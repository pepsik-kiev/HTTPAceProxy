$(document).ready(function() {

    var $connection_info_lim = $('#connection_info_lim'),
        $connection_info_cli = $('#connection_info_cli'),
        $inf_os = $('#inf_os'),
        $inf_cpu_cores = $('#inf_cpu_cores'),
        $inf_cpu_used = $('#inf_cpu_used'),
        $inf_temp = $('#inf_temp'),
        $inf_ram_total = $('#inf_ram_total'),
        $inf_ram_used = $('#inf_ram_used'),
        $inf_ram_free = $('#inf_ram_free'),
        $inf_disk_total = $('#inf_disk_total'),
        $inf_disk_used = $('#inf_disk_used'),
        $inf_disk_free = $('#inf_disk_free'),
        $inf_cpu_freq = $('#inf_cpu_freq'),
        visible_header = false;


    getStatus();

    //Help popover
    $(function () {
        $('[data-toggle="popover"]').popover({
            html: true,
            title: 'Status description.',
            content: '<span class="badge badge-pill badge-success bage-help">dl</span>' +
                        ' - Streaming content to the client<br>' +
                     '<span class="badge badge-pill badge-warning bage-help">buf</span>' +
                        ' - Data buffering. Client plays content from its buffer<br>' +
                     '<span class="badge badge-pill badge-danger bage-help">prebuf</span>' +
                        ' - Data buffering before issuing the stream url to the client<br>' +
                     '<span class="badge badge-pill badge-danger bage-help">wait</span>' +
                        ' - Expect sufficient connection speed.'
        });
    });

    // AJAX request for get status
    function getStatus() {
        $.ajax({
            url: 'http://' + window.location.host + '/stat/?action=get_status',
            type: 'get',
            success: function(resp) {
                if(resp.status === 'success') {
                    renderPage(resp);
                } else {
                    console.error('Error! getStatus() Response not returning status success');
                }
                setTimeout(getStatus, 2000);
            },
            error: function(resp, textStatus, errorThrown) {
                console.error("getStatus() Unknown error!." +
                    " ResponseCode: " + resp.status +
                    " | textStatus: " + textStatus +
                    " | errorThrown: " + errorThrown);

                $('tbody').html("");
                $('#error_resp_mess').css('display', "block");
            },
        });
    }

    // Render response data
    function renderPage(data) {
        try {
            renderHederPage(data.sys_info, data.connection_info);

            if (data.clients_data.length) {
                renderClientsTable(data.clients_data);
            } else {
                $('tbody').html('');
            }
        }
        catch(err) {
            $('#error_resp_mess').css('display', "block").html('A critical error, contact the developers.</br>' + err.name + ': ' + err.message);

            throw err;
        }
    }

    // Render Header System Info
    function renderHederPage(sys_info, connection_info) {
        $inf_os.text(sys_info.os_platform);
        $inf_cpu_cores.text("cores: " + sys_info.cpu_nums);
        $inf_cpu_used.text("used: " + ((sys_info.cpu_percent.reduce(function(a, b) { return a + b; }, 0)) / (sys_info.cpu_nums)).toFixed() + "%");
        $inf_ram_total.text("total: " + bytes2human(sys_info.mem_info['total']));
        $inf_ram_used.text("used: " + bytes2human(sys_info.mem_info['used']));
        $inf_ram_free.text("free: " + bytes2human(sys_info.mem_info['available']));
        $inf_disk_total.text("total: " + bytes2human(sys_info.disk_info['total']));
        $inf_disk_used.text("used: " + bytes2human(sys_info.disk_info['used']));
        $inf_disk_free.text("free: " + bytes2human(sys_info.disk_info['free']));

        if (sys_info.cpu_freq && sys_info.cpu_freq.current) {
            $inf_cpu_freq.text("freq: " + sys_info.cpu_freq['current'] + " Mhz");
        };

        if (sys_info.cpu_temp) {
            $inf_temp.text("CPU Temperature: " + sys_info.cpu_temp + "° C");
        };

        // Header Connection Info
        $connection_info_lim.text(connection_info.max_clients);
        $connection_info_cli.text(connection_info.total_clients);

        // Display Header System Info
        if (!visible_header) {
            if (sys_info.cpu_freq && sys_info.cpu_freq.current) $inf_cpu_freq.removeClass('d-none');
            if (sys_info.cpu_temp) $inf_temp.removeClass('d-none');
            $('.header .invisible').removeClass('invisible').removeClass('transparent');
            visible_header = true;
        }
    }

    // Render Table Body
    function renderClientsTable(clients_data) {
        var $tbody = $('tbody'),
            statusColorCss = {
                wait: 'warning',
                buf: 'warning',
                prebuf: 'danger',
                dl: 'success',
                loading: 'info',
                starting: 'info',
                idle: 'info',
                check: 'info',
            };

        clients_data.forEach(function(item, i, arr) {
            var badgeCss = typeof item.stat['status'] == "undefined" ? 'danger': statusColorCss[item.stat['status']] || 'danger',

                title_attr = 'Downloaded: ' + bytes2human((item.stat['downloaded'] || 0)) + ' Uploaded: ' + bytes2human((item.stat['uploaded'] || 0)),

                stat_peers = typeof item.stat['peers'] == "undefined" ? "" : item.stat['peers'],

                stat_status = typeof item.stat['status'] == "undefined" ? "n/a" : item.stat['status'],

                peers_html = stat_peers + '<span class="badge badge-pill badge-' + badgeCss + ' bage-fixsize">' + stat_status + '</span>',

                speed_down = typeof item.stat['speed_down'] == "undefined" ? "n/a" : item.stat['speed_down'],

                speed_up = typeof item.stat['speed_up'] == "undefined" ? "n/a" : item.stat['speed_up'],

                rowID = item.stat['sessionID'],

                $row = $('#' + rowID);

            if ($row.length === 0) {

                var clientInfo = item.clientInfo.vendor ? item.clientInfo.vendor :
                    '<i class="flag ' + (item.clientInfo.country_code.toLowerCase() || 'n/a') + '"></i>&nbsp;&nbsp;' +
                    (item.clientInfo.country_name || 'n/a') +', ' + (item.clientInfo.city || 'n/a');

                var $row = $('<tr id="' + rowID + '">' +
                              '<td><img src="' + item.channelIcon + '"/>&nbsp;&nbsp;' + item.channelName + '</td>' +
                              '<td>' + item.clientIP + '</td>'+
                              '<td>' + clientInfo + '</td>' +
                              '<td class="text-center">' + item.startTime + '</td>' +
                              '<td class="text-center duration-time">' + item.durationTime + '</td>' +
                              '<td class="text-center">' +
                                  '<div class="digit-speed text-right speed-down">'+ speed_down + '</div>' +
                                  '<img src="/stat/img/arrow-down.svg"/><img src="/stat/img/arrow-up.svg"/>' +
                                  '<div class="digit-speed text-left speed-up">' + speed_up + '</div></td>' +
                              '<td class="text-center peers">'+ peers_html + '</td>' +
                          '</tr>').data('update', true).attr('title', title_attr);

                $tbody.append($row);

            } else {
                $row.attr('title', title_attr);
                $row.find('.duration-time').text(item.durationTime);
                $row.find('.speed-down').text(item.stat['speed_down']);
                $row.find('.speed-up').text(item.stat['speed_up']);
                $row.find('.peers').html(peers_html);
                $row.data('update', true);
            }
        });

        $('tbody tr').each(function(index) {
            if ($(this).data('update') === false) {
                $(this).remove();
            };
        }).data('update', false);
    }

    // Convert byte format to kB, MB, GB, TB
    function bytes2human(size) {
        var i = size == 0 ? 0 : Math.floor( Math.log(size) / Math.log(1024) );
        return ( size / Math.pow(1024, i) ).toFixed(2) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i];
    };

});

