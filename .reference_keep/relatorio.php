<?php
// relatorio.php - Relatórios e Análises
require 'db.php';

// Obter período para relatório
$periodo = $_GET['periodo'] ?? '7d';
$tipo = $_GET['tipo'] ?? 'consumo';

// Definir intervalo
switch($periodo) {
    case '1d': $interval = '1 DAY'; $group_format = '%H:00'; $date_format = 'H:i'; break;
    case '7d': $interval = '7 DAY'; $group_format = '%Y-%m-%d'; $date_format = 'd/m'; break;
    case '30d': $interval = '30 DAY'; $group_format = '%Y-%m-%d'; $date_format = 'd/m'; break;
    case '90d': $interval = '90 DAY'; $group_format = '%Y-%u'; $date_format = 'W'; break;
    default: $interval = '7 DAY'; $group_format = '%Y-%m-%d'; $date_format = 'd/m';
}

// Relatório de Consumo/Variação
if($tipo == 'consumo') {
    $sql = "
        SELECT 
            d.name as device_name,
            DATE_FORMAT(r.ts, '$group_format') as period,
            MIN(r.volume_m3) as volume_min,
            MAX(r.volume_m3) as volume_max,
            AVG(r.percentual) as level_avg,
            COUNT(*) as readings_count
        FROM readings r
        JOIN devices d ON r.device_id = d.device_id
        WHERE r.ts > NOW() - INTERVAL $interval
        GROUP BY d.name, DATE_FORMAT(r.ts, '$group_format')
        ORDER BY d.name, r.ts DESC
    ";
    $dados = $pdo->query($sql)->fetchAll();
}

// Relatório de Eventos
elseif($tipo == 'eventos') {
    $sql = "
        SELECT 
            d.name as device_name,
            e.event_type,
            e.severity,
            COUNT(*) as count,
            MAX(e.ts) as last_occurrence
        FROM events e
        JOIN devices d ON e.device_id = d.device_id
        WHERE e.ts > NOW() - INTERVAL $interval
        GROUP BY d.name, e.event_type, e.severity
        ORDER BY count DESC
    ";
    $dados = $pdo->query($sql)->fetchAll();
}

// Relatório de Eficiência
elseif($tipo == 'eficiencia') {
    $sql = "
        SELECT 
            d.name as device_name,
            d.type,
            COUNT(r.id) as total_readings,
            AVG(r.percentual) as avg_level,
            STDDEV(r.percentual) as level_variance,
            MIN(r.percentual) as min_level,
            MAX(r.percentual) as max_level,
            AVG(CASE WHEN r.pressure_bar > 0 THEN r.pressure_bar END) as avg_pressure
        FROM devices d
        LEFT JOIN readings r ON d.device_id = r.device_id 
            AND r.ts > NOW() - INTERVAL $interval
        GROUP BY d.device_id, d.name, d.type
        ORDER BY avg_level DESC
    ";
    $dados = $pdo->query($sql)->fetchAll();
}

// Estatísticas gerais do período
$stats = $pdo->query("
    SELECT 
        COUNT(DISTINCT d.device_id) as total_devices,
        COUNT(r.id) as total_readings,
        AVG(r.percentual) as avg_level,
        COUNT(DISTINCT e.id) as total_events
    FROM devices d
    LEFT JOIN readings r ON d.device_id = r.device_id 
        AND r.ts > NOW() - INTERVAL $interval
    LEFT JOIN events e ON d.device_id = e.device_id 
        AND e.ts > NOW() - INTERVAL $interval
")->fetch();

// Função para calcular score de eficiência
function calcularScore($data) {
    $level_score = min(100, $data['avg_level'] ?? 0);
    $stability_score = 100 - min(100, ($data['level_variance'] ?? 0) * 2);
    $readings_score = min(100, ($data['total_readings'] ?? 0) / 100 * 100);
    
    return round(($level_score + $stability_score + $readings_score) / 3, 1);
}
?>
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="utf-8">
    <title>xAguada - Relatórios</title>
    <link rel="stylesheet" href="style.css">
    <style>
        .report-controls {
            background: #f8f9fa;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            display: flex;
            gap: 20px;
            align-items: center;
            flex-wrap: wrap;
        }
        .stats-overview {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-box {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            color: #007bff;
        }
        .report-table {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .report-table table {
            width: 100%;
            margin: 0;
        }
        .report-table th {
            background: #007bff;
            color: white;
            padding: 15px;
            text-align: left;
        }
        .report-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }
        .report-table tr:hover {
            background: #f8f9fa;
        }
        .button.active {
            background: #007bff;
            color: white;
        }
        .score {
            padding: 5px 10px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
        }
        .score.high { background: #28a745; }
        .score.medium { background: #ffc107; color: #333; }
        .score.low { background: #dc3545; }
        .chart-mini {
            display: inline-block;
            width: 60px;
            height: 20px;
            background: linear-gradient(to right, #e9ecef 0%, #007bff 100%);
            border-radius: 10px;
            position: relative;
        }
        .chart-mini::after {
            content: '';
            position: absolute;
            left: var(--progress, 50%);
            top: 2px;
            bottom: 2px;
            width: 4px;
            background: white;
            border-radius: 2px;
        }
    </style>
</head>
<body>
    <h1>📊 xAguada - Relatórios</h1>
    
    <!-- Controles do Relatório -->
    <div class="report-controls">
        <div>
            <label>Período:</label>
            <a href="?tipo=<?= $tipo ?>&periodo=1d" class="button <?= $periodo == '1d' ? 'active' : '' ?>">1 dia</a>
            <a href="?tipo=<?= $tipo ?>&periodo=7d" class="button <?= $periodo == '7d' ? 'active' : '' ?>">7 dias</a>
            <a href="?tipo=<?= $tipo ?>&periodo=30d" class="button <?= $periodo == '30d' ? 'active' : '' ?>">30 dias</a>
            <a href="?tipo=<?= $tipo ?>&periodo=90d" class="button <?= $periodo == '90d' ? 'active' : '' ?>">90 dias</a>
        </div>
        
        <div>
            <label>Tipo:</label>
            <a href="?periodo=<?= $periodo ?>&tipo=consumo" class="button <?= $tipo == 'consumo' ? 'active' : '' ?>">📈 Consumo</a>
            <a href="?periodo=<?= $periodo ?>&tipo=eventos" class="button <?= $tipo == 'eventos' ? 'active' : '' ?>">🚨 Eventos</a>
            <a href="?periodo=<?= $periodo ?>&tipo=eficiencia" class="button <?= $tipo == 'eficiencia' ? 'active' : '' ?>">⚡ Eficiência</a>
        </div>
        
        <div>
            <a href="dashboard.php" class="button">← Dashboard</a>
            <a href="historico.php" class="button">📈 Histórico</a>
        </div>
    </div>

    <!-- Estatísticas Gerais -->
    <div class="stats-overview">
        <div class="stat-box">
            <div class="stat-number"><?= $stats['total_devices'] ?></div>
            <div>Dispositivos Ativos</div>
        </div>
        <div class="stat-box">
            <div class="stat-number"><?= number_format($stats['total_readings']) ?></div>
            <div>Leituras no Período</div>
        </div>
        <div class="stat-box">
            <div class="stat-number"><?= number_format($stats['avg_level'], 1) ?>%</div>
            <div>Nível Médio</div>
        </div>
        <div class="stat-box">
            <div class="stat-number"><?= $stats['total_events'] ?></div>
            <div>Eventos Registrados</div>
        </div>
    </div>

    <!-- Relatório de Consumo -->
    <?php if($tipo == 'consumo'): ?>
    <div class="report-table">
        <h3 style="margin: 0; padding: 20px; background: #f8f9fa; border-bottom: 1px solid #ddd;">
            📈 Relatório de Consumo - Últimos <?= $periodo == '1d' ? '1 dia' : ($periodo == '7d' ? '7 dias' : ($periodo == '30d' ? '30 dias' : '90 dias')) ?>
        </h3>
        <table>
            <thead>
                <tr>
                    <th>Dispositivo</th>
                    <th>Período</th>
                    <th>Volume Min (m³)</th>
                    <th>Volume Max (m³)</th>
                    <th>Variação (m³)</th>
                    <th>Nível Médio (%)</th>
                    <th>Leituras</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach($dados as $row): ?>
                <?php $variacao = $row['volume_max'] - $row['volume_min']; ?>
                <tr>
                    <td><strong><?= htmlspecialchars($row['device_name']) ?></strong></td>
                    <td><?= $row['period'] ?></td>
                    <td><?= number_format($row['volume_min'], 2) ?></td>
                    <td><?= number_format($row['volume_max'], 2) ?></td>
                    <td style="color: <?= $variacao > 0 ? '#28a745' : ($variacao < 0 ? '#dc3545' : '#6c757d') ?>">
                        <?= number_format($variacao, 2) ?>
                    </td>
                    <td>
                        <div class="chart-mini" style="--progress: <?= $row['level_avg'] ?>%"></div>
                        <?= number_format($row['level_avg'], 1) ?>%
                    </td>
                    <td><?= $row['readings_count'] ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <!-- Relatório de Eventos -->
    <?php elseif($tipo == 'eventos'): ?>
    <div class="report-table">
        <h3 style="margin: 0; padding: 20px; background: #f8f9fa; border-bottom: 1px solid #ddd;">
            🚨 Relatório de Eventos - Últimos <?= $periodo == '1d' ? '1 dia' : ($periodo == '7d' ? '7 dias' : ($periodo == '30d' ? '30 dias' : '90 dias')) ?>
        </h3>
        <table>
            <thead>
                <tr>
                    <th>Dispositivo</th>
                    <th>Tipo de Evento</th>
                    <th>Severidade</th>
                    <th>Ocorrências</th>
                    <th>Última Ocorrência</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach($dados as $row): ?>
                <tr>
                    <td><strong><?= htmlspecialchars($row['device_name']) ?></strong></td>
                    <td><?= htmlspecialchars($row['event_type']) ?></td>
                    <td>
                        <span class="<?= strtolower($row['severity']) ?>" style="padding: 2px 8px; border-radius: 12px;">
                            <?= $row['severity'] ?>
                        </span>
                    </td>
                    <td><?= $row['count'] ?></td>
                    <td><?= date('d/m/Y H:i', strtotime($row['last_occurrence'])) ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <!-- Relatório de Eficiência -->
    <?php elseif($tipo == 'eficiencia'): ?>
    <div class="report-table">
        <h3 style="margin: 0; padding: 20px; background: #f8f9fa; border-bottom: 1px solid #ddd;">
            ⚡ Relatório de Eficiência - Últimos <?= $periodo == '1d' ? '1 dia' : ($periodo == '7d' ? '7 dias' : ($periodo == '30d' ? '30 dias' : '90 dias')) ?>
        </h3>
        <table>
            <thead>
                <tr>
                    <th>Dispositivo</th>
                    <th>Tipo</th>
                    <th>Score Eficiência</th>
                    <th>Nível Médio (%)</th>
                    <th>Estabilidade</th>
                    <th>Leituras</th>
                    <th>Pressão Média</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach($dados as $row): ?>
                <?php 
                $score = calcularScore($row);
                $score_class = $score >= 80 ? 'high' : ($score >= 60 ? 'medium' : 'low');
                $stability = 100 - min(100, ($row['level_variance'] ?? 0) * 2);
                ?>
                <tr>
                    <td><strong><?= htmlspecialchars($row['device_name']) ?></strong></td>
                    <td><?= htmlspecialchars($row['type']) ?></td>
                    <td>
                        <span class="score <?= $score_class ?>"><?= $score ?></span>
                    </td>
                    <td>
                        <div class="chart-mini" style="--progress: <?= $row['avg_level'] ?>%"></div>
                        <?= number_format($row['avg_level'] ?? 0, 1) ?>%
                    </td>
                    <td><?= number_format($stability, 1) ?>%</td>
                    <td><?= $row['total_readings'] ?></td>
                    <td><?= $row['avg_pressure'] ? number_format($row['avg_pressure'], 1) . ' bar' : '-' ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>
    <?php endif; ?>

    <!-- Ações Recomendadas -->
    <div class="card">
        <h3>💡 Recomendações</h3>
        <?php if($tipo == 'eficiencia'): ?>
        <ul>
            <?php foreach($dados as $row): 
                $score = calcularScore($row);
                if($score < 60): ?>
                <li><strong><?= $row['device_name'] ?>:</strong> Score baixo (<?= $score ?>). Verificar funcionamento e calibração.</li>
            <?php endif; 
            endforeach; ?>
            <li>Dispositivos com alta variância de nível podem indicar problemas de vazamento ou sensor.</li>
            <li>Monitore dispositivos com poucas leituras - podem ter problemas de conectividade.</li>
        </ul>
        <?php elseif($tipo == 'eventos'): ?>
        <ul>
            <li>Eventos críticos frequentes requerem atenção imediata.</li>
            <li>Padrões de eventos podem indicar problemas sistemáticos.</li>
            <li>Configure alertas automáticos para eventos de alta severidade.</li>
        </ul>
        <?php else: ?>
        <ul>
            <li>Grandes variações de volume podem indicar vazamentos ou uso intensivo.</li>
            <li>Monitore tendências de consumo para prever necessidades de abastecimento.</li>
            <li>Níveis consistentemente baixos podem requerer aumento da capacidade.</li>
        </ul>
        <?php endif; ?>
    </div>

    <p><small>Relatório gerado em: <?= date('d/m/Y H:i:s') ?></small></p>
</body>
</html>
