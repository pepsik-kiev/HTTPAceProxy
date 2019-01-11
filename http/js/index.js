getStatus();


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
            $('main').append('<h1 class="text-center" style="color:red; font-weight: bold;">Server not responding! Refresh page!!!</h1>')
        },
    });
}


function renderPage(data) {
    var sys_info = data.sys_info;
    var connection_info = data.connection_info;
    var clients_data = data.clients_data;
    var clients_content = "";
    $('#sys_info').html("OS " + sys_info.os_platform + "&nbsp;CPU cores: " + sys_info.cpu_nums +
                        " used: " + sys_info.cpu_percent + "%</br>"+
                        "RAM &nbsp;total: " + sys_info.total_ram +
                        " &nbsp;used: " + sys_info.used_ram +
                        "&nbsp;free: " + sys_info.free_ram + "</br>DISK &nbsp;total: " + sys_info.total_disk +
                        "&nbsp;used: " + sys_info.used_disk + "&nbsp;free: " + sys_info.free_disk);
    $('#connection_info').html("Connections limit: " + connection_info.max_clients +
                               "&nbsp;&nbsp;&nbsp;Connected clients: " + connection_info.total_clients);
    if (clients_data.length) {
        clients_data.forEach(function(item, i, arr) {
            var badgeCss = "info";

            if (item.status === "buf") {
                badgeCss = "warning";
            } else if (item.status === "prebuf") {
                badgeCss = "danger";
            } else if (item.status === "dl") {
                badgeCss = "success";
            } else {
                badgeCss = "danger";
            }

            clients_content += '<tr title="Downloaded: ' + item.downloaded + ' Uploaded: ' + item.uploaded + '">'+
                                '<td><img src="' + item.channelIcon + '"/>&nbsp;&nbsp;' + item.channelName + '</td>' +
                                '<td>' + item.clientIP + '</td>'+
                                '<td>' + item.clientLocation + '</td>' +
                                '<td class="text-center">' + item.startTime + '</td>' +
                                '<td class="text-center">' + item.durationTime + '</td>' +
                                '<td class="text-center">' +
                                    '<div class="digit-speed text-right">'+ item.streamSpeedDL + '</div>' +
                                    '<img src="/stat/img/arrow-down.svg"/><img src="/stat/img/arrow-up.svg"/>' +
                                    '<div class="digit-speed text-left">' + item.streamSpeedUL + '</div></td>' +
                                '<td class="text-center">'+ item.streamPeers +
                                '<span class="badge badge-pill badge-'+ badgeCss +' bage-fixsize">' + item.status +'</span></td></tr>';
        });
        $('tbody').html(clients_content);
    } else {
        $('tbody').html('');
    }
}