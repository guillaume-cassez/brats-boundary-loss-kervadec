"""
MedNeXt-B + Kervadec boundary loss (MIDL 2019) - paper 3 BRATS.

Inherits from nnUNetTrainerMedNeXtDistMap (paper 1) to reuse:
  - MedNeXt-B architecture, BF16 setup, AdamW + PolyLR, deep supervision,
    deterministic seeding, checkpoint serialization base.

Overrides to swap the auxiliary regression task for a direct boundary loss:
  - NO _dist_head (no extra Conv3d)
  - SDT precomputed offline in voxel units, clamp [-theta0, +theta0], int8
  - Loss: total = seg_loss + lambda * mean(sigmoid(pred_logits) * sdt_signed)
  - SDT cache directory: sdt_cache_kervadec_t{theta0}

Env overrides:
  KERVADEC_LAMBDA: float, default 1.0
  KERVADEC_THETA0: int, default 30 (must match precomputed cache directory)

Reference:
  Kervadec H. et al., "Boundary loss for highly unbalanced segmentation",
  MIDL 2019 / MedIA 2021.
"""

import os
import numpy as np
import torch
import torch.nn.functional as F
from torch import autocast

from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
from nnunetv2.utilities.helpers import dummy_context

from nnunetv2.training.nnUNetTrainer.variants.loss.nnUNetTrainerMedNeXtDistMap import (
    nnUNetTrainerMedNeXtDistMap,
)

try:
    import blosc2
except ImportError:
    blosc2 = None


def kervadec_boundary_loss(pred_logits: torch.Tensor, sdt: torch.Tensor) -> torch.Tensor:
    """
    Kervadec MIDL 2019 boundary loss for region-based 3D segmentation.
    Loss = mean(sigmoid(pred_logits) * sdt_signed)
    sdt < 0 inside region, > 0 outside, clamped to [-theta0, +theta0].
    """
    return (torch.sigmoid(pred_logits) * sdt).mean()


class nnUNetTrainerMedNeXtKervadec(nnUNetTrainerMedNeXtDistMap):
    """MedNeXt-B + Kervadec boundary loss (no auxiliary head)."""

    _num_epochs = 300
    _lambda_kervadec = 1.0
    _theta0 = 30  # must match precompute_sdt_kervadec.py output dir suffix

    def __init__(self, plans, configuration, fold, dataset_json, device=torch.device('cuda')):
        super().__init__(plans, configuration, fold, dataset_json, device)

        # Lambda from env (Kervadec-specific, independent of DISTMAP_LAMBDA)
        if 'KERVADEC_LAMBDA' in os.environ:
            self._lambda_kervadec = float(os.environ['KERVADEC_LAMBDA'])
        if 'KERVADEC_THETA0' in os.environ:
            self._theta0 = int(os.environ['KERVADEC_THETA0'])

        # Override SDT cache directory to Kervadec precompute (voxel units, clamp theta0)
        preproc = os.environ.get('nnUNet_preprocessed', '')
        ds_dir = os.path.join(preproc, 'Dataset001_BraTS2023GLI')
        self.sdt_dir = os.path.join(ds_dir, f'sdt_cache_kervadec_t{self._theta0}')

        self._epoch_boundary_losses = []

    # --- Initialization: skip _dist_head creation ---

    def initialize(self):
        # Call grandparent (nnUNetTrainer) directly, skipping DistMap which creates _dist_head
        nnUNetTrainer.initialize(self)
        self.batch_size = 1  # VRAM constraint, fair comparison with paper 1
        self._dist_head = None  # explicit: no auxiliary head for Kervadec

    # --- on_train_start: skip decoder hook, log Kervadec config ---

    def on_train_start(self):
        # Call grandparent on_train_start (skip DistMap which hooks decoder + logs DistMap config)
        nnUNetTrainer.on_train_start(self)

        if self._seed > 0:
            self.print_to_log_file(f'Seed: {self._seed} (torch + numpy + random)')
        else:
            self.print_to_log_file('WARNING: no seed set (non-deterministic)')

        self._sdt_available = os.path.isdir(self.sdt_dir) and blosc2 is not None
        if self._sdt_available:
            n = len([f for f in os.listdir(self.sdt_dir) if f.endswith('_sdt.b2nd')])
            self.print_to_log_file(
                f'Kervadec SDT cache: {n} files in {self.sdt_dir}'
            )
            self.print_to_log_file(
                f'Lambda={self._lambda_kervadec:.4f}, theta0={self._theta0} vox'
            )
        else:
            self.print_to_log_file(
                f'ERROR: Kervadec SDT cache missing at {self.sdt_dir}'
            )
            raise FileNotFoundError(
                f'SDT cache required at {self.sdt_dir} - run scripts/precompute_sdt_kervadec.py first'
            )

        n_backbone = sum(p.numel() for p in self.network.parameters())
        self.print_to_log_file(
            f'Architecture: MedNeXt-B ({n_backbone / 1e6:.2f}M params), no auxiliary head'
        )
        self.print_to_log_file(
            f'Loss: nnU-Net seg_loss + lambda * mean(sigmoid(pred) * sdt_signed)'
        )
        self.print_to_log_file(
            f'Config: AdamW lr={self.initial_lr:.0e} wd={self.weight_decay:.0e}, '
            f'PolyLR exp=0.9, batch=1'
        )

    # --- Epoch start: reset boundary loss accumulator, skip dist_head .train() ---

    def on_train_epoch_start(self):
        nnUNetTrainer.on_train_epoch_start(self)
        new_lr = self._poly_lr(self.current_epoch)
        for pg in self.optimizer.param_groups:
            pg['lr'] = new_lr
        self._epoch_seg_losses = []
        self._epoch_boundary_losses = []

    def on_validation_epoch_start(self):
        nnUNetTrainer.on_validation_epoch_start(self)

    # --- SDT loading: pad with theta0 (Kervadec) instead of 1.0 (Ma 2020) ---

    def _load_sdt_batch_kervadec(self, keys, spatial_shape):
        if not self._sdt_available:
            return None
        sdts = []
        for key in keys:
            p = os.path.join(self.sdt_dir, key + '_sdt.b2nd')
            if not os.path.exists(p):
                return None
            sdts.append(np.asarray(blosc2.open(p)).astype(np.float32))
        sdt_t = torch.from_numpy(np.stack(sdts))
        sz, sy, sx = sdt_t.shape[2], sdt_t.shape[3], sdt_t.shape[4]
        tz, ty, tx = spatial_shape
        if sz != tz or sy != ty or sx != tx:
            # Pad with theta0 (= "far outside region" in Kervadec convention)
            sdt_t = F.pad(
                sdt_t,
                [0, tx - sx, 0, ty - sy, 0, tz - sz],
                value=float(self._theta0),
            )
        return sdt_t.to(self.device)

    # --- Training step: replace MSE aux loss with Kervadec boundary loss ---

    def train_step(self, batch):
        data = batch['data']
        target = batch['target']
        keys = batch['keys']

        data = data.to(self.device, non_blocking=True)
        if isinstance(target, list):
            target = [i.to(self.device, non_blocking=True) for i in target]
        else:
            target = target.to(self.device, non_blocking=True)

        self.optimizer.zero_grad(set_to_none=True)

        with autocast(self.device.type, enabled=True) if self.device.type == 'cuda' else dummy_context():
            output = self.network(data)
            seg_loss = self.loss(output, target)

            total_loss = seg_loss
            boundary_loss_val = 0.0

            if self._lambda_kervadec > 0:
                # Use main resolution logits (first in deep supervision list if applicable)
                if isinstance(output, (list, tuple)):
                    main_logits = output[0]
                else:
                    main_logits = output
                spatial = main_logits.shape[2:]

                sdt_gt = self._load_sdt_batch_kervadec(keys, spatial)
                if sdt_gt is not None:
                    boundary_loss = kervadec_boundary_loss(main_logits, sdt_gt)
                    total_loss = seg_loss + self._lambda_kervadec * boundary_loss
                    boundary_loss_val = boundary_loss.detach().cpu().item()

        if self.grad_scaler is not None:
            self.grad_scaler.scale(total_loss).backward()
            self.grad_scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 12)
            self.grad_scaler.step(self.optimizer)
            self.grad_scaler.update()
        else:
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 12)
            self.optimizer.step()

        self._epoch_seg_losses.append(seg_loss.detach().cpu().item())
        if boundary_loss_val != 0.0:
            self._epoch_boundary_losses.append(boundary_loss_val)

        return {'loss': total_loss.detach().cpu().numpy()}

    # --- Epoch end: log seg/boundary/total decomposition ---

    def on_train_epoch_end(self, train_outputs):
        nnUNetTrainer.on_train_epoch_end(self, train_outputs)
        if self._epoch_seg_losses:
            seg_mean = float(np.mean(self._epoch_seg_losses))
            bnd_mean = float(np.mean(self._epoch_boundary_losses)) if self._epoch_boundary_losses else 0.0
            total = seg_mean + self._lambda_kervadec * bnd_mean
            self.print_to_log_file(
                f'Loss decomposition: seg={seg_mean:.4f} boundary={bnd_mean:.4f} '
                f'(x{self._lambda_kervadec:.4f}={self._lambda_kervadec * bnd_mean:.4f}) '
                f'total={total:.4f}'
            )

    # --- Checkpoint: persist Kervadec metadata, skip dist_head ---

    def save_checkpoint(self, filename: str) -> None:
        # Call grandparent directly (skip DistMap which writes dist_head_weights)
        nnUNetTrainer.save_checkpoint(self, filename)
        if self.local_rank == 0 and not self.disable_checkpointing:
            checkpoint = torch.load(filename, map_location=self.device, weights_only=False)
            checkpoint['lambda_kervadec'] = self._lambda_kervadec
            checkpoint['theta0'] = self._theta0
            torch.save(checkpoint, filename)

    def load_checkpoint(self, filename_or_checkpoint) -> None:
        if isinstance(filename_or_checkpoint, str):
            checkpoint = torch.load(filename_or_checkpoint, map_location=self.device, weights_only=False)
        else:
            checkpoint = filename_or_checkpoint

        if 'lambda_kervadec' in checkpoint and 'KERVADEC_LAMBDA' not in os.environ:
            self._lambda_kervadec = checkpoint['lambda_kervadec']
        if 'theta0' in checkpoint and 'KERVADEC_THETA0' not in os.environ:
            self._theta0 = checkpoint['theta0']

        # Call grandparent directly (skip DistMap which loads dist_head_weights)
        nnUNetTrainer.load_checkpoint(self, filename_or_checkpoint)


# --- Variant classes ---


class nnUNetTrainerMedNeXtKervadec_3ep(nnUNetTrainerMedNeXtKervadec):
    _num_epochs = 3


class nnUNetTrainerMedNeXtKervadec_10ep(nnUNetTrainerMedNeXtKervadec):
    _num_epochs = 10


class nnUNetTrainerMedNeXtKervadec_50ep(nnUNetTrainerMedNeXtKervadec):
    _num_epochs = 50
