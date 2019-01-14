getStatus();


$(function () {
    $('[data-toggle="popover"]').popover({
        html: true,
        title: 'Status description.',
        content: '<span class="badge badge-pill badge-success bage-help">dl</span>' +
                    ' - Streaming data to the client<br>' +
                 '<span class="badge badge-pill badge-warning bage-help">buf</span>' +
                    ' - Data buffering. Client plays data from its buffer<br>' +
                 '<span class="badge badge-pill badge-danger bage-help">prebuf</span>' +
                    ' - Data buffering before issuing the stream url to the client<br>' +
                 '<span class="badge badge-pill badge-danger bage-help">wait</span>' +
                    ' - Expect sufficient connection speed.'
    })
})

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
            $('#error_resp_mess').css('display', "block")
        },
    });
}


function renderPage(data) {
    var sys_info = data.sys_info;
    var connection_info = data.connection_info;
    var clients_data = data.clients_data;
    var clients_content = "";
    var cpu_temp = sys_info.cpu_temp ? "CPU Temperature: " + sys_info.cpu_temp + "&#176; C</br>" : "";

    $('#sys_info').html("OS " + sys_info.os_platform + "&nbsp;CPU cores: " + sys_info.cpu_nums +
                        " used: " + sys_info.cpu_percent + "%</br>"+
                        cpu_temp +
                        "RAM &nbsp;total: " + bytes2human(sys_info.mem_info['total']) +
                        " &nbsp;used: " + bytes2human(sys_info.mem_info['used']) +
                        "&nbsp;free: " + bytes2human(sys_info.mem_info['available']) +
                        "</br>" +
                        "DISK &nbsp;total: " + bytes2human(sys_info.disk_info['total']) +
                        "&nbsp;used: " + bytes2human(sys_info.disk_info['used']) +
                        "&nbsp;free: " + bytes2human(sys_info.disk_info['free']));

    $('#connection_info_lim').text(connection_info.max_clients);
    $('#connection_info_cli').text(connection_info.total_clients);

    if (clients_data.length) {
        clients_data.forEach(function(item, i, arr) {

            var statusColorCss = {
                wait: 'warning',
                buf: 'warning',
                prebuf: 'danger',
                dl: 'success',
            };

            var badgeCss = statusColorCss[item.stat['status']] || 'danger';

            var clientInfo = item.clientInfo.vendor ? item.clientInfo.vendor :
                '<i class="flag ' + (item.clientInfo.country_code || 'n/a') + '"></i>&nbsp;&nbsp;' +
                (item.clientInfo.country_name || 'n/a') +', ' + (item.clientInfo.city || 'n/a');

            clients_content += '<tr title="Downloaded: ' + bytes2human(item.stat['downloaded']) + ' Uploaded: ' + bytes2human(item.stat['uploaded']) + '">'+
                                '<td><img src="' + item.channelIcon + '"/>&nbsp;&nbsp;' + item.channelName + '</td>' +
                                '<td>' + item.clientIP + '</td>'+
                                '<td>' + clientInfo + '</td>' +
                                '<td class="text-center">' + item.startTime + '</td>' +
                                '<td class="text-center">' + item.durationTime + '</td>' +
                                '<td class="text-center">' +
                                    '<div class="digit-speed text-right">'+ item.stat['speed_down'] + '</div>' +
                                    '<img src="/stat/img/arrow-down.svg"/><img src="/stat/img/arrow-up.svg"/>' +
                                    '<div class="digit-speed text-left">' + item.stat['speed_up'] + '</div></td>' +
                                '<td class="text-center">'+ item.stat['peers'] +
                                '<span class="badge badge-pill badge-'+ badgeCss + ' bage-fixsize">' + item.stat['status'] + '</span></td></tr>';

        });

        $('tbody').html(clients_content);
    } else {

        $('tbody').html('');
    }
}

function bytes2human(size) {
    var i = size == 0 ? 0 : Math.floor( Math.log(size) / Math.log(1024) );
    return ( size / Math.pow(1024, i) ).toFixed(2) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i];
}
